/**
 * Vay Reports - single-file Google Apps Script
 *
 * Required source sheets:
 *   sales   : Date, Party Name, Sales Rep, Net Amount (tax-inclusive)
 *   receipt : Date, Account Name, Sales Rep, Amount
 *   arr     : Account Name, Balance, Days, Group
 *   items   : Date, Item Name, Qty, Rate
 *   stock   : Item Name, Qty, P.Price
 *   payments: Date, Account Name, Amount  (P&L only)
 *
 * Reporting rules:
 *   MTD             = first day of report month through report date
 *   Last 15 days    = report date and preceding 14 days
 *   Last 2/3 months = rolling periods ending on report date
 *   YTD             = April 1 through report date
 *
 * Phases for setDateAndGenerateReport(dateStr, phase):
 *   core       = sales/account/group/follow-up
 *   fiscal     = fiscal monthly sales-rep, group, and account reports
 *   items      = item sales/qty (no profit)
 *   profit     = password-protected monthly P&L only
 *   expenses   = password-protected expense sheets (run separately)
 *   itemprofit = password-protected item-wise profit reports
 *
 * Run each phase as a separate job on a large workbook. Reports stay in
 * this spreadsheet. Each report opens one tab (getSheetByName or insertSheet)
 * and overwrites it in chunks, with retries on Spreadsheet timeouts.
 *
 * Credit ageing is estimated because the source data has no invoice-level
 * outstanding allocation. Receipts are assumed to settle older invoices first.
 * arr.Days is shown as AR Days alongside that estimate.
 */

var VAY_CONFIG = {
  sourceSheets: ["sales", "receipt", "arr", "stock", "items", "payments"],
  fixedReportSheets: [
    "sales_rep_performance_report",
    "fiscal_monthly_sales_rep_performance_report",
    "fiscal_monthly_account_performance_report",
    "fiscal_monthly_group_performance_report",
    "account_performance_report",
    "group_performance_report",
    "item_wise_sales",
    "item_wise_profit",
    "item_wise_monthly_profit",
    "item_wise_monthly_qty",
    "item_cost_exceptions",
    "source_data_warnings",
    "monthly_profit_report",
    "expense_by_category",
    "expense_by_account",
    "unmapped_payment_accounts"
  ],
  profitPasswordSha256: "78a2e8535ac364cdad81b7e39bde8f85527bdbf44066ce2f1df3750830cd291e",
  salesTaxInclusiveRate: 0.18,
  paymentCategories: {
    "Travel Expenses": ["RAHUL_EXPENSE", "SAKARIYA_EXPENCE", "FUEL_EXPENSE", "VEHICLE EXPENSE", "Vehicle maintenance"],
    "Courier": ["COURIER CHARGE", "EASY_PARCEL", "NEST_DP", "DREAMS_DP"],
    "Office Expenses": [
      "OFFICE_STATIONARY_EXPENCE", "OFFICE_ELECTRICITY_EXPENCE", "OFFICE_FOOD_EXPENCE",
      "OTHER_OFFICE_MISE_EXPENCE", "Electricity and water charges", "Electrical Fittings",
      "RENT SHOP PAYABLE", "Donation and charity", "MARKETING_EXPENSE", "AMAL_TRADERS", 
      "ZAINU EXPENCE", "JIJIETTAN_EXPENCE", "Carriage inward"
    ],
    "Salary": [
      "SAKARIYA _SALARY", "SAKARIYA_SALARY", "JIJIETTAN_SALARY", "RIFAIE _SALARY", "RIFAIE_SALARY",
      "ISMAIL_SALARY", "ABDULLAH KOYA_SALARY", "RAHUL_SALARY", "ZAINU_SALARY",
      "ABHILASH_SALARY"
    ],
    "Compliance Expenses": ["SAREENA K_SALARY"],
    "Investment Returns": [
      "AYISHA_YASMIN_INVESTMENT", "RASMILA_INVESTMENT", "YASIRA_BEEVI_INVESTMENT",
      "ISMAIL CARE OF_NASEEB INVESTMENT", "ISMAIL CARE OF_MIDHLAJ INVESTMENT",
      "ISMAIL CARE OF_JIBNA INVESTMENT", "RIFAIE_CARE OF_KADHEEJA INVESTMENT"
    ],
    "Purchase": [
      "RAHMA ASSOCIATES_VENDOR", "HINDPRAKASH INDUSTRIES LIMITED",
      "IC SOLUTIONS"
    ],
    "Bank Inward": ["HDFC BANK", "FEDERAL BANK-3698"],
    "RD": ["COMPANY RD", "COMPANY RD2", "COMPANY RD3"]
  },
  followUpPrefixes: ["sales_follow_up_", "collection_follow_up_"],
  defaultSalesRep: "NO_REP",
  defaultReceiptRep: "INVESTMENT",
  defaultParty: "NO_PARTY_NAME",
  defaultGroup: "NO_GROUP",
  textHeaders: [
    "Status", "Stock Status", "Issue", "Type", "Source", "Key", "Detail",
    "Message", "Report", "Customer", "Account Name", "Group", "Sales Rep",
    "Item Name", "Generated At", "Report Date", "Timezone", "Phase", "Export Folder",
    "Line", "Category"
  ],
  statusColors: {
    "SUCCESS": "#d9ead3",
    "FAILED": "#f4cccc",
    "SKIPPED": "#fff2cc",
    "URGENT": "#f4cccc",
    "FOLLOW UP": "#fff2cc",
    "WATCH": "#cfe2f3",
    "NEWLY INACTIVE": "#ead1dc",
    "DORMANT": "#d9d9d9",
    "EXCESS STOCK": "#f4cccc",
    "LOW STOCK": "#fce5cd",
    "OK": "#d9ead3"
  }
};

var VAY_SS = null;
var VAY_TABLE_CACHE = null;
var VAY_TIMEZONE = null;
var VAY_PAYMENT_MAP = null;
var VAY_PROFIT_AUTH = false;
var VAY_MAX_WARNING_ROWS = 200;
var VAY_WRITE_CHUNK_ROWS = 750;
var VAY_SHEETS_RETRIES = 4;
var VAY_SHEETS_RETRY_MS = 2000;

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("Vay Reports")
    .addItem("1. Pre-process + generate core", "preProcessAndGenerate")
    .addItem("2. Generate core reports", "generateCoreReports")
    .addItem("3. Generate fiscal monthly reports", "generateFiscalReports")
    .addItem("4. Generate item reports", "generateItemReports")
    .addItem("5. Generate P&L reports", "generateProfitReports")
    .addItem("6. Generate expense reports", "generateExpenseReports")
    .addItem("7. Generate item profit reports", "generateItemProfitReports")
    .addItem("8. Export reports to PDF", "exportSheets")
    .addSeparator()
    .addItem("Delete generated reports", "deleteReports")
    .addItem("Delete follow-up sheets only", "deleteFollowUpSheets")
    .addToUi();
}

function preProcess() {
  return withDocumentLock_(function () {
    return preProcessUnlocked_();
  });
}

function preProcessUnlocked_() {
  resetRuntimeCache_();
  var ss = activeSpreadsheet_();
  var results = [];
  var arr = rewriteSourceSheet_("arr", function (headers, index, rows) {
    var next = dropExactTotalRows_(rows, index["Account Name"]);
    fillBlankInRows_(next, index.Balance, 0);
    fillBlankInRows_(next, index.Days, 0);
    if (!rowsHaveValue_(next, index["Account Name"], VAY_CONFIG.defaultParty)) {
      var row = Array(headers.length).fill("");
      row[index["Account Name"]] = VAY_CONFIG.defaultParty;
      if (index.Balance !== undefined) row[index.Balance] = 0;
      if (index.Days !== undefined) row[index.Days] = 0;
      if (index.Group !== undefined) row[index.Group] = VAY_CONFIG.defaultGroup;
      next.push(row);
    }
    return next;
  });
  results.push(arr.message);

  var groupMap = {};
  arr.rows.forEach(function (r) {
    var account = cleanText_(r[arr.index["Account Name"]]);
    if (account) groupMap[account.toLowerCase()] = cleanText_(r[arr.index.Group]) || VAY_CONFIG.defaultGroup;
  });

  results.push(rewriteSourceSheet_("sales", function (headers, index, rows) {
    var next = dropExactTotalRows_(rows, index["Party Name"]);
    fillBlankInRows_(next, index["Sales Rep"], VAY_CONFIG.defaultSalesRep);
    fillBlankInRows_(next, index["Party Name"], VAY_CONFIG.defaultParty);
    normalizeDateInRows_(next, index.Date);
    var groupIndex = index.Group;
    if (groupIndex === undefined) {
      headers.push("Group");
      groupIndex = headers.length - 1;
      next.forEach(function (row) { row[groupIndex] = ""; });
    }
    next.forEach(function (row) {
      var key = cleanText_(row[index["Party Name"]]).toLowerCase();
      row[groupIndex] = groupMap[key] || VAY_CONFIG.defaultGroup;
    });
    return next;
  }).message);

  results.push(rewriteSourceSheet_("receipt", function (headers, index, rows) {
    var next = dropExactTotalRows_(rows, index["Account Name"]);
    fillBlankInRows_(next, index["Sales Rep"], VAY_CONFIG.defaultReceiptRep);
    normalizeDateInRows_(next, index.Date);
    return next;
  }).message);

  results.push(rewriteSourceSheet_("items", function (headers, index, rows) {
    var next = dropExactTotalRows_(rows, index["Item Name"]);
    normalizeDateInRows_(next, index.Date);
    return next;
  }).message);

  resetRuntimeCache_();
  ss.toast("Pre-processing completed", "Vay Reports", 5);
  Logger.log(results.join("\n"));
  return results;
}

function generateCoreReports() {
  return generateReportsForPhase_("core");
}

function generateFiscalReports() {
  return generateReportsForPhase_("fiscal");
}

function generateItemReports() {
  return generateReportsForPhase_("items");
}

function generateProfitReports() {
  return generatePasswordPhase_("profit");
}

function generateExpenseReports() {
  return generatePasswordPhase_("expenses");
}

function generateItemProfitReports() {
  return generatePasswordPhase_("itemprofit");
}

function generatePasswordPhase_(phase) {
  if (!requireProfitPassword_()) {
    SpreadsheetApp.getUi().alert("Incorrect password or cancelled.");
    return;
  }
  VAY_PROFIT_AUTH = true;
  try {
    return generateReportsForPhase_(phase);
  } finally {
    VAY_PROFIT_AUTH = false;
  }
}

function generateReportsForPhase_(phase) {
  var input = promptReportDate_();
  if (input === null) return;
  var result = setDateAndGenerateReport(input, phase);
  SpreadsheetApp.getUi().alert(result.message);
  return result;
}

function preProcessAndGenerate() {
  var input = promptReportDate_();
  if (input === null) return;
  var result = withDocumentLock_(function () {
    preProcessUnlocked_();
    return setDateAndGenerateReportUnlocked_(input, "core");
  });
  SpreadsheetApp.getUi().alert(result.message);
  return result;
}

function setDateAndGenerateReport(dateStr, phase) {
  return withDocumentLock_(function () {
    return setDateAndGenerateReportUnlocked_(dateStr, phase);
  });
}

function setDateAndGenerateReportUnlocked_(dateStr, phase) {
  phase = normalizePhase_(phase || "core");
  if (isProfitTaskPhase_(phase) && !VAY_PROFIT_AUTH) {
    throw new Error("Profit reports can only be generated from the password-protected menu.");
  }
  var reportDate = parseReportDate_(dateStr);
  var statuses = generateFor(reportDate, phase);
  PropertiesService.getDocumentProperties().setProperty(
    "VAY_LAST_REPORT_DATE",
    formatDate_(reportDate, "yyyy-MM-dd")
  );
  var failures = statuses.filter(function (s) { return s.status === "FAILED"; });
  var skipped = statuses.filter(function (s) { return s.status === "SKIPPED"; });
  var message = "All reports generated for " + formatDate_(reportDate, "yyyy-MM-dd");
  if (failures.length) {
    message = (statuses.length - failures.length) + " reports completed; " + failures.length + " failed.";
  } else if (skipped.length) {
    message = (statuses.length - skipped.length) + " report(s) written. Run this menu again for the next sheet.";
  }
  return {
    ok: failures.length === 0,
    message: message,
    statuses: statuses
  };
}

function generateFor(reportDate, phase) {
  phase = normalizePhase_(phase);
  var started = Date.now();
  resetRuntimeCache_();
  var ctx = buildReportContext_(reportDate);
  ctx.phase = phase;
  var statusByName = {};
  var statuses = [];
  var itemsLoaded = phase === "items" || phase === "itemprofit" || phase === "profit";
  var aborted = false;
  var fiscalProgress = phase === "fiscal" ? loadFiscalProgress_(reportDate) : null;
  var wroteFiscalThisRun = false;

  try {
    preloadSourceTables_(phase);
    if (itemsLoaded) ctx.inventory = stockMap_();

    reportTasks_().forEach(function (task) {
      if (aborted) return;
      if (isProfitTaskPhase_(task.phase) && !isProfitTaskPhase_(phase)) return;
      if (!taskShouldRun_(task, phase)) return;
      if (fiscalProgress && fiscalProgress.done[task.name]) {
        statuses.push([task.name, "SUCCESS", 0, "Already written for this date"]);
        statusByName[task.name] = "SUCCESS";
        return;
      }
      if (wroteFiscalThisRun) {
        statuses.push([task.name, "SKIPPED", 0, "Run Generate fiscal monthly reports again to write this sheet"]);
        statusByName[task.name] = "SKIPPED";
        return;
      }
      if (task.dependsOn && statusByName[task.dependsOn] !== "SUCCESS") {
        var skipMessage = statusByName[task.dependsOn]
          ? "Skipped because " + task.dependsOn + " " + String(statusByName[task.dependsOn]).toLowerCase()
          : "Skipped because " + task.dependsOn + " did not run";
        statuses.push([task.name, "SKIPPED", 0, skipMessage]);
        statusByName[task.name] = "SKIPPED";
        return;
      }
      if ((task.phase === "items" || task.phase === "itemprofit") && !itemsLoaded) {
        preloadSourceTables_(task.phase === "itemprofit" ? "itemprofit" : "items");
        ctx.inventory = stockMap_();
        itemsLoaded = true;
      }
      try {
        var count = task.fn(ctx);
        statuses.push([task.name, "SUCCESS", Number(count || 0), ""]);
        statusByName[task.name] = "SUCCESS";
        if (fiscalProgress) {
          fiscalProgress.done[task.name] = true;
          saveFiscalProgress_(fiscalProgress);
          wroteFiscalThisRun = true;
        }
      } catch (error) {
        statuses.push([task.name, "FAILED", 0, error.message || String(error)]);
        statusByName[task.name] = "FAILED";
        Logger.log(task.name + " failed: " + (error.stack || error));
        if (isSpreadsheetTimeout_(error)) aborted = true;
      }
    });
  } catch (error) {
    statuses.push(["Generate", "FAILED", 0, error.message || String(error)]);
    Logger.log("generateFor aborted: " + (error.stack || error));
  }

  if (phase !== "profit" && phase !== "expenses" && phase !== "fiscal") {
    try {
      writeGenerationStatus_(ctx, statuses, Date.now() - started, "");
    } catch (error) {
      Logger.log("report_generation_status write skipped: " + (error.stack || error));
    }
  }
  return statuses.map(function (row) {
    return { report: row[0], status: row[1], rows: row[2], message: row[3] };
  });
}

function reportTasks_() {
  return [
    { name: "Sales rep performance", phase: "core", fn: generateSalesRepPerformanceReport_ },
    { name: "Account performance", phase: "core", fn: generateAccountPerformanceReport_ },
    { name: "Group performance", phase: "core", dependsOn: "Account performance", fn: generateGroupPerformanceReport_ },
    { name: "Sales follow-up", phase: "core", dependsOn: "Account performance", fn: generateSalesFollowUpSheets_ },
    { name: "Collection follow-up", phase: "core", dependsOn: "Account performance", fn: generateCollectionFollowUpSheets_ },
    { name: "Fiscal monthly group performance", phase: "fiscal", fn: generateFiscalMonthlyGroupPerformanceReport_ },
    { name: "Fiscal monthly sales and collection", phase: "fiscal", fn: generateFiscalMonthlySalesAndCollectionReport_ },
    { name: "Fiscal monthly account performance", phase: "fiscal", fn: generateFiscalMonthlyAccountPerformanceReport_ },
    { name: "Item-wise sales", phase: "items", fn: generateItemWiseSalesReport_ },
    { name: "Item cost exceptions", phase: "items", fn: generateItemCostExceptions_ },
    { name: "Item monthly quantity", phase: "items", fn: generateItemWiseMonthlyQtyReport_ },
    { name: "Monthly profit", phase: "profit", fn: generateMonthlyProfitReport_ },
    { name: "Expense by category", phase: "expenses", fn: generateExpenseByCategoryReport_ },
    { name: "Unmapped payment accounts", phase: "expenses", fn: generateUnmappedPaymentAccounts_ },
    { name: "Expense by account", phase: "expenses", fn: generateExpenseByAccountReport_ },
    { name: "Item-wise profit", phase: "itemprofit", fn: generateItemWiseProfitReport_ },
    { name: "Item monthly profit", phase: "itemprofit", fn: generateItemWiseMonthlyProfitReport_ },
    { name: "Source data warnings", phase: "always", fn: generateSourceDataWarnings_ }
  ];
}

function generateSourceDataWarnings_(ctx) {
  var warnings = [];
  var includeCoreSources = ctx.phase === "core";
  var includeItems = ctx.phase === "items" || ctx.phase === "itemprofit" || ctx.phase === "profit";
  var includePayments = ctx.phase === "profit";
  var emptyTable = function (sheetName) {
    return { sheetName: sheetName, headers: [], index: {}, rows: [] };
  };
  var arr = includeCoreSources ? tryReadTable_("arr", ["Account Name"]) : emptyTable("arr");
  var sales = includeCoreSources ? tryReadTable_("sales", ["Party Name", "Net Amount", "Date"]) : emptyTable("sales");
  var receipts = includeCoreSources ? tryReadTable_("receipt", ["Account Name", "Amount", "Date"]) : emptyTable("receipt");
  var items = includeItems
    ? tryReadTable_("items", ["Item Name", "Qty", "Rate", "Date"])
    : emptyTable("items");
  var stock = includeItems
    ? tryReadTable_("stock", ["Item Name", "Qty", "P.Price"])
    : emptyTable("stock");
  var reportDateLabel = formatDate_(ctx.reportDate, "yyyy-MM-dd");

  var sourceTables = [];
  var payments = includePayments
    ? tryReadTable_("payments", ["Date", "Account Name", "Amount"])
    : emptyTable("payments");
  if (includeCoreSources) sourceTables = sourceTables.concat([arr, sales, receipts]);
  if (includeItems) sourceTables = sourceTables.concat([items, stock]);
  if (includePayments) sourceTables.push(payments);
  sourceTables.forEach(function (table) {
    if (table.error) warnings.push(["Missing source", table.sheetName, "", table.error]);
  });

  var arrNames = {};
  arr.rows.forEach(function (r) {
    var name = cleanText_(r[arr.index["Account Name"]]);
    if (!name) return;
    var key = name.toLowerCase();
    if (arrNames[key]) {
      warnings.push(["Duplicate ARR account", "arr", name, "Duplicates '" + arrNames[key] + "'"]);
    } else {
      arrNames[key] = name;
    }
    if (arr.index.Balance !== undefined && number_(r[arr.index.Balance]) < 0) {
      warnings.push(["Negative amount", "arr", name, "Balance is negative"]);
    }
  });

  var unmatchedSales = {};
  var futureSales = 0;
  var invalidSalesDates = 0;
  var negativeSales = 0;
  var noRep = 0;
  var noParty = 0;
  sales.rows.forEach(function (r) {
    var party = cleanText_(r[sales.index["Party Name"]]);
    var amount = number_(r[sales.index["Net Amount"]]);
    var d = date_(r[sales.index.Date]);
    var rep = cleanText_(r[sales.index["Sales Rep"]]);
    if (party === VAY_CONFIG.defaultParty || !party) noParty++;
    if (rep === VAY_CONFIG.defaultSalesRep || !rep) noRep++;
    if (party && !arrNames[party.toLowerCase()]) {
      unmatchedSales[party.toLowerCase()] = unmatchedSales[party.toLowerCase()] || { name: party, count: 0 };
      unmatchedSales[party.toLowerCase()].count++;
    }
    if (!d) invalidSalesDates++;
    else if (d > ctx.reportDate) futureSales++;
    if (amount < 0) negativeSales++;
  });
  addCountWarning_(warnings, unmatchedSales, "Unmatched party", "sales", "sales rows not in arr");
  addSummaryWarning_(warnings, "Future dates", "sales", futureSales, "rows after " + reportDateLabel + " (excluded from reports)");
  addSummaryWarning_(warnings, "Invalid dates", "sales", invalidSalesDates, "rows with an unreadable Date");
  addSummaryWarning_(warnings, "Negative amount", "sales", negativeSales, "rows with Net Amount < 0");
  addSummaryWarning_(warnings, "Default value", "sales", noRep, "rows using " + VAY_CONFIG.defaultSalesRep);
  addSummaryWarning_(warnings, "Default value", "sales", noParty, "rows using " + VAY_CONFIG.defaultParty);

  var unmatchedReceipts = {};
  var futureReceipts = 0;
  var invalidReceiptDates = 0;
  var negativeReceipts = 0;
  var investment = 0;
  receipts.rows.forEach(function (r) {
    var account = cleanText_(r[receipts.index["Account Name"]]);
    var amount = number_(r[receipts.index.Amount]);
    var d = date_(r[receipts.index.Date]);
    var rep = cleanText_(r[receipts.index["Sales Rep"]]);
    if (rep === VAY_CONFIG.defaultReceiptRep || !rep) investment++;
    if (account && !arrNames[account.toLowerCase()]) {
      unmatchedReceipts[account.toLowerCase()] = unmatchedReceipts[account.toLowerCase()] || { name: account, count: 0 };
      unmatchedReceipts[account.toLowerCase()].count++;
    }
    if (!d) invalidReceiptDates++;
    else if (d > ctx.reportDate) futureReceipts++;
    if (amount < 0) negativeReceipts++;
  });
  addCountWarning_(warnings, unmatchedReceipts, "Unmatched party", "receipt", "receipt rows not in arr");
  addSummaryWarning_(warnings, "Future dates", "receipt", futureReceipts, "rows after " + reportDateLabel + " (excluded from reports)");
  addSummaryWarning_(warnings, "Invalid dates", "receipt", invalidReceiptDates, "rows with an unreadable Date");
  addSummaryWarning_(warnings, "Negative amount", "receipt", negativeReceipts, "rows with Amount < 0");
  addSummaryWarning_(warnings, "Default value", "receipt", investment, "rows using " + VAY_CONFIG.defaultReceiptRep);

  if (includeItems) {
    var missingCost = {};
    var futureItems = 0;
    var invalidItemDates = 0;
    var negativeItems = 0;
    var inventory = {};
    try { inventory = inventory_(ctx); } catch (e) { inventory = {}; }
    items.rows.forEach(function (r) {
      var name = cleanText_(r[items.index["Item Name"]]);
      var qty = number_(r[items.index.Qty]);
      var rate = number_(r[items.index.Rate]);
      var d = date_(r[items.index.Date]);
      if (!d) invalidItemDates++;
      else if (d > ctx.reportDate) futureItems++;
      if (qty < 0 || rate < 0) negativeItems++;
      if (name && (!inventory[name] || inventory[name].cost === null)) missingCost[name] = true;
    });
    var missingNames = Object.keys(missingCost);
    missingNames.slice(0, 50).forEach(function (name) {
      warnings.push(["Missing item cost", "items", name, "No valid P.Price in stock"]);
    });
    if (missingNames.length > 50) {
      warnings.push(["Missing item cost", "items", "", (missingNames.length - 50) + " more items with no valid P.Price"]);
    }
    addSummaryWarning_(warnings, "Future dates", "items", futureItems, "rows after " + reportDateLabel + " (excluded from reports)");
    addSummaryWarning_(warnings, "Invalid dates", "items", invalidItemDates, "rows with an unreadable Date");
    addSummaryWarning_(warnings, "Negative amount", "items", negativeItems, "rows with Qty < 0 or Rate < 0");
  }

  if (includePayments) {
    var futurePayments = 0;
    var invalidPaymentDates = 0;
    payments.rows.forEach(function (r) {
      var d = date_(r[payments.index.Date]);
      if (!d) invalidPaymentDates++;
      else if (d > ctx.reportDate) futurePayments++;
    });
    addSummaryWarning_(warnings, "Future dates", "payments", futurePayments, "rows after " + reportDateLabel + " (excluded from reports)");
    addSummaryWarning_(warnings, "Invalid dates", "payments", invalidPaymentDates, "rows with an unreadable Date");
  }

  if (warnings.length > VAY_MAX_WARNING_ROWS) {
    var omitted = warnings.length - VAY_MAX_WARNING_ROWS;
    warnings = warnings.slice(0, VAY_MAX_WARNING_ROWS);
    warnings.push(["Truncated", "", "", omitted + " more warnings omitted"]);
  }

  writeReport_("source_data_warnings", ["Type", "Source", "Key", "Detail"], warnings, null);
  return warnings.length;
}

function generateSalesRepPerformanceReport_(ctx) {
  var sales = readTable_("sales", ["Sales Rep", "Net Amount", "Date"]);
  var receipts = readTable_("receipt", ["Sales Rep", "Amount", "Date"]);
  var summaries = {};

  function add(rep, amount, date, type) {
    rep = cleanText_(rep) || (type === "sales" ? VAY_CONFIG.defaultSalesRep : VAY_CONFIG.defaultReceiptRep);
    if (rep === VAY_CONFIG.defaultReceiptRep) return;
    if (!date || date > ctx.reportDate) return;
    if (!summaries[rep]) summaries[rep] = newPeriodSummary_();
    addPeriodAmount_(summaries[rep], type, amount, date, ctx);
  }

  sales.rows.forEach(function (r) {
    add(r[sales.index["Sales Rep"]], number_(r[sales.index["Net Amount"]]), date_(r[sales.index.Date]), "sales");
  });
  receipts.rows.forEach(function (r) {
    add(r[receipts.index["Sales Rep"]], number_(r[receipts.index.Amount]), date_(r[receipts.index.Date]), "collection");
  });

  var rows = Object.keys(summaries).map(function (rep) {
    var s = summaries[rep];
    return [rep, s.mtdSales, s.mtdCollection, s.d15Sales, s.d15Collection,
      s.m2Sales, s.m2Collection, s.m3Sales, s.m3Collection, s.ytdSales, s.ytdCollection];
  });
  rows.sort(function (a, b) { return b[9] - a[9]; });
  writeReport_("sales_rep_performance_report", [
    "Sales Rep", "MTD Sales", "MTD Collection", "15 Days Sales", "15 Days Collection",
    "2 Months Sales", "2 Months Collection", "3 Months Sales", "3 Months Collection",
    "YTD Sales", "YTD Collection"
  ], rows, totalRow_(rows, 11, "TOTAL", 1));
  return rows.length;
}

function generateFiscalMonthlySalesAndCollectionReport_(ctx) {
  var sales = readTable_("sales", ["Sales Rep", "Net Amount", "Date"]);
  var receipts = readTable_("receipt", ["Sales Rep", "Amount", "Date"]);
  var reps = {};
  var reportFiscalIndex = fiscalMonthIndex_(ctx.reportDate.getMonth());

  function add(row, table, amountHeader, type) {
    var rep = cleanText_(row[table.index["Sales Rep"]]) || (type === 0 ? VAY_CONFIG.defaultSalesRep : VAY_CONFIG.defaultReceiptRep);
    if (rep === VAY_CONFIG.defaultReceiptRep) return;
    var d = date_(row[table.index.Date]);
    if (!d || d < ctx.fiscalYearStart || d > ctx.reportDate) return;
    if (!reps[rep]) reps[rep] = Array(24).fill(0);
    reps[rep][fiscalMonthIndex_(d.getMonth()) * 2 + type] += number_(row[table.index[amountHeader]]);
  }

  sales.rows.forEach(function (r) { add(r, sales, "Net Amount", 0); });
  receipts.rows.forEach(function (r) { add(r, receipts, "Amount", 1); });

  var rows = Object.keys(reps).map(function (rep) {
    return fiscalMonthRowFromValues_([rep], reps[rep], reportFiscalIndex);
  });
  rows.sort(function (a, b) { return b[25] - a[25]; });
  var total = totalRow_(rows, 27, "Total", 1);
  blankFutureFiscalMonthRow_(total, reportFiscalIndex, 1);
  writeReport_(
    "fiscal_monthly_sales_rep_performance_report",
    ["Sales Rep"].concat(fiscalMonthPairHeaders_(ctx)),
    rows,
    total,
    { skipFormat: true }
  );
  return rows.length;
}

function accountGroupMap_() {
  var arr = readTable_("arr", ["Account Name"]);
  var map = {};
  arr.rows.forEach(function (r) {
    var name = cleanText_(r[arr.index["Account Name"]]);
    if (!name) return;
    map[name.toLowerCase()] = (arr.index.Group !== undefined ? cleanText_(r[arr.index.Group]) : "") || VAY_CONFIG.defaultGroup;
  });
  return map;
}

function fiscalMonthPairHeaders_(ctx) {
  var months = fiscalMonths_(ctx.fiscalYearStart);
  var reportFiscalIndex = fiscalMonthIndex_(ctx.reportDate.getMonth());
  var headers = [];
  months.forEach(function (m, i) {
    var suffix = i > reportFiscalIndex ? " [after report date]" : "";
    headers.push(formatDate_(m, "MMMM yyyy") + " Sales" + suffix);
    headers.push(formatDate_(m, "MMMM yyyy") + " Collection" + suffix);
  });
  headers.push("Total Sales", "Total Collection");
  return headers;
}

function fiscalMonthRowFromValues_(labelCells, values, reportFiscalIndex) {
  var next = values.slice();
  var totalSales = 0;
  var totalCollection = 0;
  for (var i = 0; i < 24; i += 2) {
    totalSales += next[i];
    totalCollection += next[i + 1];
  }
  blankFutureFiscalPairs_(next, reportFiscalIndex);
  return labelCells.concat(next, [totalSales, totalCollection]);
}

function fiscalAccountMonths_(ctx) {
  if (ctx.fiscalAccounts) return ctx.fiscalAccounts;
  var groupMap = accountGroupMap_();
  var sales = readTable_("sales", ["Party Name", "Net Amount", "Date"]);
  var receipts = readTable_("receipt", ["Account Name", "Amount", "Date", "Sales Rep"]);
  var accounts = {};

  function ensure(name) {
    name = cleanText_(name) || VAY_CONFIG.defaultParty;
    var key = name.toLowerCase();
    if (!accounts[key]) {
      accounts[key] = {
        name: name,
        group: groupMap[key] || VAY_CONFIG.defaultGroup,
        values: Array(24).fill(0)
      };
    }
    return accounts[key];
  }

  sales.rows.forEach(function (r) {
    var d = date_(r[sales.index.Date]);
    if (!d || d < ctx.fiscalYearStart || d > ctx.reportDate) return;
    ensure(r[sales.index["Party Name"]]).values[fiscalMonthIndex_(d.getMonth()) * 2] += number_(r[sales.index["Net Amount"]]);
  });
  receipts.rows.forEach(function (r) {
    var rep = cleanText_(r[receipts.index["Sales Rep"]]) || VAY_CONFIG.defaultReceiptRep;
    if (rep === VAY_CONFIG.defaultReceiptRep) return;
    var d = date_(r[receipts.index.Date]);
    if (!d || d < ctx.fiscalYearStart || d > ctx.reportDate) return;
    ensure(r[receipts.index["Account Name"]]).values[fiscalMonthIndex_(d.getMonth()) * 2 + 1] += number_(r[receipts.index.Amount]);
  });

  ctx.fiscalAccounts = Object.keys(accounts).map(function (key) { return accounts[key]; });
  return ctx.fiscalAccounts;
}

function generateFiscalMonthlyGroupPerformanceReport_(ctx) {
  var reportFiscalIndex = fiscalMonthIndex_(ctx.reportDate.getMonth());
  var groups = {};
  fiscalAccountMonths_(ctx).forEach(function (a) {
    var group = a.group || VAY_CONFIG.defaultGroup;
    if (!groups[group]) groups[group] = Array(24).fill(0);
    for (var i = 0; i < 24; i++) groups[group][i] += a.values[i];
  });
  var rows = Object.keys(groups).map(function (group) {
    return fiscalMonthRowFromValues_([group], groups[group], reportFiscalIndex);
  });
  rows.sort(function (a, b) { return b[25] - a[25]; });
  var total = totalRow_(rows, 27, "Total", 1);
  blankFutureFiscalMonthRow_(total, reportFiscalIndex, 1);
  writeReport_(
    "fiscal_monthly_group_performance_report",
    ["Group"].concat(fiscalMonthPairHeaders_(ctx)),
    rows,
    total,
    { skipFormat: true }
  );
  return rows.length;
}

function generateFiscalMonthlyAccountPerformanceReport_(ctx) {
  var reportFiscalIndex = fiscalMonthIndex_(ctx.reportDate.getMonth());
  var rows = fiscalAccountMonths_(ctx).map(function (a) {
    return fiscalMonthRowFromValues_([a.name, a.group], a.values, reportFiscalIndex);
  });
  rows.sort(function (a, b) { return b[26] - a[26]; });
  var total = totalRow_(rows, 28, "Total", 2);
  blankFutureFiscalMonthRow_(total, reportFiscalIndex, 2);
  writeReport_(
    "fiscal_monthly_account_performance_report",
    ["Account Name", "Group"].concat(fiscalMonthPairHeaders_(ctx)),
    rows,
    total,
    { skipFormat: true }
  );
  return rows.length;
}

function generateAccountPerformanceReport_(ctx) {
  var sales = readTable_("sales", ["Party Name", "Net Amount", "Date"]);
  var receipts = readTable_("receipt", ["Account Name", "Amount", "Date", "Sales Rep"]);
  var arr = readTable_("arr", ["Account Name", "Group", "Balance"]);
  var accounts = {};

  function ensure(name) {
    name = cleanText_(name) || VAY_CONFIG.defaultParty;
    var key = name.toLowerCase();
    if (!accounts[key]) {
      accounts[key] = {
        name: name, group: VAY_CONFIG.defaultGroup, arDays: 0, balance: 0,
        summary: newPeriodSummary_(),
        d0to15Sales: 0, d16to30Sales: 0, d31to60Sales: 0, olderSales: 0,
        salesLast10: 0, salesLast15: 0, salesLast20: 0, salesLast25: 0, salesLast30: 0,
        overdue30: 0, overdue15: 0, newCredit: 0,
        bal10Plus: 0, bal15Plus: 0, bal20Plus: 0, bal25Plus: 0, bal30Plus: 0
      };
    }
    return accounts[key];
  }

  arr.rows.forEach(function (r) {
    var name = cleanText_(r[arr.index["Account Name"]]);
    if (!name) return;
    var a = ensure(name);
    a.group = cleanText_(r[arr.index.Group]) || VAY_CONFIG.defaultGroup;
    a.balance = number_(r[arr.index.Balance]);
    a.arDays = arr.index.Days !== undefined ? number_(r[arr.index.Days]) : 0;
  });

  sales.rows.forEach(function (r) {
    var d = date_(r[sales.index.Date]);
    if (!d || d > ctx.reportDate) return;
    var a = ensure(r[sales.index["Party Name"]]);
    var amount = number_(r[sales.index["Net Amount"]]);
    addPeriodAmount_(a.summary, "sales", amount, d, ctx);
    if (d >= ctx.last10Start) a.salesLast10 += amount;
    if (d >= ctx.last15Start) a.salesLast15 += amount;
    if (d >= ctx.last20Start) a.salesLast20 += amount;
    if (d >= ctx.last25Start) a.salesLast25 += amount;
    if (d >= ctx.last30Start) a.salesLast30 += amount;
    if (d >= ctx.last15Start) a.d0to15Sales += amount;
    else if (d >= ctx.last30Start) a.d16to30Sales += amount;
    else if (d >= ctx.last60Start) a.d31to60Sales += amount;
    else a.olderSales += amount;
  });

  receipts.rows.forEach(function (r) {
    var rep = cleanText_(r[receipts.index["Sales Rep"]]) || VAY_CONFIG.defaultReceiptRep;
    if (rep === VAY_CONFIG.defaultReceiptRep) return;
    var d = date_(r[receipts.index.Date]);
    if (!d || d > ctx.reportDate) return;
    var a = ensure(r[receipts.index["Account Name"]]);
    addPeriodAmount_(a.summary, "collection", number_(r[receipts.index.Amount]), d, ctx);
  });

  ctx.accounts = Object.keys(accounts).map(function (key) {
    var a = accounts[key];
    var ageing = estimateAgeing_(Math.max(0, a.balance), [a.d0to15Sales, a.d16to30Sales, a.d31to60Sales, a.olderSales]);
    a.overdue30 = ageing[2] + ageing[3];
    a.overdue15 = ageing[1];
    a.newCredit = ageing[0];
    var outstanding = Math.max(0, a.balance);
    a.bal10Plus = Math.max(0, outstanding - a.salesLast10);
    a.bal15Plus = Math.max(0, outstanding - a.salesLast15);
    a.bal20Plus = Math.max(0, outstanding - a.salesLast20);
    a.bal25Plus = Math.max(0, outstanding - a.salesLast25);
    a.bal30Plus = Math.max(0, outstanding - a.salesLast30);
    return a;
  });
  ctx.accounts.sort(function (a, b) { return b.summary.ytdSales - a.summary.ytdSales; });

  var rows = ctx.accounts.map(function (a) {
    var s = a.summary;
    return [
      a.name, a.group, a.arDays, s.mtdSales, s.mtdCollection, s.m2Sales, s.m2Collection,
      s.m3Sales, s.m3Collection, s.ytdSales, s.ytdCollection, a.balance,
      a.overdue30, a.overdue15, a.newCredit,
      a.d0to15Sales, a.d16to30Sales, a.d31to60Sales, a.olderSales
    ];
  });
  var headers = [
    "Account Name", "Group", "AR Days", "MTD Sales", "MTD Collection", "2 Months Sales", "2 Months Collection",
    "3 Months Sales", "3 Months Collection", "YTD Sales", "YTD Collection", "Balance",
    "30 Days Credit Lapsed", "15 Days Credit Lapsed", "New Credit Added",
    "Sales in Last 15 Days", "Sales Between 15 to 30 Days",
    "Sales Between 30 to 60 Days", "Sales Before 60 Days"
  ];
  writeReport_("account_performance_report", headers, rows, totalRow_(rows, 19, "Total", 3));
  return rows.length;
}

function generateGroupPerformanceReport_(ctx) {
  requireAccounts_(ctx);
  var metricKeys = [
    ["mtdSales", "MTD Sales"], ["mtdCollection", "MTD Collection"],
    ["m2Sales", "2 Months Sales"], ["m2Collection", "2 Months Collection"],
    ["m3Sales", "3 Months Sales"], ["m3Collection", "3 Months Collection"],
    ["ytdSales", "YTD Sales"], ["ytdCollection", "YTD Collection"],
    ["balance", "Balance"], ["overdue30", "30 Days Credit Lapsed"],
    ["overdue15", "15 Days Credit Lapsed"], ["newCredit", "New Credit Added"]
  ];
  var groups = {};

  ctx.accounts.forEach(function (a) {
    var group = a.group || VAY_CONFIG.defaultGroup;
    if (!groups[group]) groups[group] = Array(metricKeys.length).fill(0);
    metricKeys.forEach(function (metric, i) {
      var value = a.summary[metric[0]] !== undefined ? a.summary[metric[0]] : a[metric[0]];
      groups[group][i] += number_(value);
    });
  });

  var rows = Object.keys(groups).map(function (g) { return [g].concat(groups[g]); });
  rows.sort(function (a, b) { return b[1] - a[1]; });
  writeReport_("group_performance_report", ["Group"].concat(metricKeys.map(function (m) { return m[1]; })), rows, totalRow_(rows, 13, "Total", 1));
  return rows.length;
}

function generateSalesFollowUpSheets_(ctx) {
  requireAccounts_(ctx);
  var groups = {};

  ctx.accounts.forEach(function (a) {
    if (a.summary.mtdSales !== 0) return;
    var hasHistory = a.summary.ytdSales !== 0 || a.d0to15Sales !== 0 || a.d16to30Sales !== 0 ||
      a.d31to60Sales !== 0 || a.olderSales !== 0 || a.summary.m2Sales !== 0 || a.summary.m3Sales !== 0;
    if (!hasHistory) return;
    var group = a.group || VAY_CONFIG.defaultGroup;
    if (!groups[group]) groups[group] = [];
    var status = a.d0to15Sales > 0 ? "NEWLY INACTIVE" : (a.d16to30Sales > 0 ? "FOLLOW UP" : (a.d31to60Sales > 0 ? "URGENT" : "DORMANT"));
    groups[group].push([
      a.name, status, a.summary.mtdSales, a.d0to15Sales, a.d16to30Sales, a.d31to60Sales, a.olderSales,
      a.summary.m2Sales, a.summary.m3Sales, a.summary.ytdSales, a.balance
    ]);
  });

  var headers = [
    "Customer", "Status", "MTD Sales", "Last 15 Days Sales", "15 to 30 Days Sales",
    "30 to 60 Days Sales", "Before 60 Days Sales", "2 Months Sales", "3 Months Sales", "YTD Sales", "Balance"
  ];
  Object.keys(groups).forEach(function (group) {
    groups[group].sort(function (a, b) {
      var priority = { "URGENT": 4, "FOLLOW UP": 3, "NEWLY INACTIVE": 2, "DORMANT": 1 };
      return (priority[b[1]] - priority[a[1]]) || (b[9] - a[9]);
    });
  });
  return writeFollowUpGroupSheets_(VAY_CONFIG.followUpPrefixes[0], groups, headers, { statusHeader: "Status" });
}

function generateCollectionFollowUpSheets_(ctx) {
  requireAccounts_(ctx);
  var groups = {};

  ctx.accounts.forEach(function (a) {
    if (a.balance <= 0) return;
    var status = a.bal30Plus > 0 ? "URGENT" : (a.bal15Plus > 0 ? "FOLLOW UP" : "WATCH");
    var group = a.group || VAY_CONFIG.defaultGroup;
    if (!groups[group]) groups[group] = [];
    groups[group].push([
      a.name, status, a.summary.mtdCollection, a.summary.m2Collection, a.summary.m3Collection,
      a.balance, a.bal10Plus, a.bal15Plus, a.bal20Plus, a.bal25Plus, a.bal30Plus
    ]);
  });

  var headers = [
    "Customer", "Status", "MTD Collection", "2 Months Collection", "3 Months Collection",
    "Balance", "10+ Days Balance", "15+ Days Balance", "20+ Days Balance", "25+ Days Balance", "30+ Days Balance"
  ];
  Object.keys(groups).forEach(function (group) {
    groups[group].sort(function (a, b) {
      var priority = { "URGENT": 3, "FOLLOW UP": 2, "WATCH": 1 };
      return (priority[b[1]] - priority[a[1]]) || (b[10] - a[10]) || (b[7] - a[7]) || (b[5] - a[5]);
    });
  });
  return writeFollowUpGroupSheets_(VAY_CONFIG.followUpPrefixes[1], groups, headers, { statusHeader: "Status" });
}

function generateItemWiseSalesReport_(ctx) {
  var rows = itemSummaries_(ctx).salesRows;
  writeReport_("item_wise_sales", ["Item Name", "MTD Qty", "MTD Sales", "Last Month Sales", "Last 3 Months Sales", "YTD Sales"], rows, totalRow_(rows, 6, "Total", 1));
  return rows.length;
}

function generateItemWiseProfitReport_(ctx) {
  var data = itemSummaries_(ctx);
  writeReport_("item_wise_profit", ["Item Name", "MTD Qty", "MTD Profit", "Last Month Profit", "Last 3 Months Profit", "YTD Profit"], data.profitRows, totalRow_(data.profitRows, 6, "Total", 1));
  return data.profitRows.length;
}

function generateItemCostExceptions_(ctx) {
  var data = itemSummaries_(ctx);
  writeReport_("item_cost_exceptions", ["Item Name", "Issue"], data.missingRows, null);
  return data.missingRows.length;
}

function generateItemWiseMonthlyProfitReport_(ctx) {
  var data = itemSummaries_(ctx);
  writeReport_("item_wise_monthly_profit", ["Item Name"].concat(fiscalMonthNames_(), ["Total"]), data.monthlyProfitRows, data.monthlyProfitTotal);
  return data.monthlyProfitRows.length;
}

function generateItemWiseMonthlyQtyReport_(ctx) {
  var data = itemSummaries_(ctx);
  writeReport_(
    "item_wise_monthly_qty",
    ["Item Name"].concat(fiscalMonthNames_(), ["Avg Last 3 Completed Months", "Total", "Current Stock", "Stock Status"]),
    data.monthlyQtyRows,
    null,
    { statusHeader: "Stock Status" }
  );
  return data.monthlyQtyRows.length;
}

function paymentKey_(name) {
  return cleanText_(name).toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
}

function paymentKeyCompact_(name) {
  return paymentKey_(name).replace(/\s+/g, "");
}

function paymentCategoryMap_() {
  if (VAY_PAYMENT_MAP) return VAY_PAYMENT_MAP;
  VAY_PAYMENT_MAP = {};
  Object.keys(VAY_CONFIG.paymentCategories).forEach(function (category) {
    VAY_CONFIG.paymentCategories[category].forEach(function (name) {
      VAY_PAYMENT_MAP[paymentKey_(name)] = category;
      VAY_PAYMENT_MAP[paymentKeyCompact_(name)] = category;
    });
  });
  return VAY_PAYMENT_MAP;
}

function paymentCategory_(name) {
  var key = paymentKey_(name);
  var map = paymentCategoryMap_();
  if (map[key]) return map[key];
  var compact = paymentKeyCompact_(name);
  if (map[compact]) return map[compact];
  if (/(^|\s)salary$/.test(key)) return "Salary";
  if (/\binvestment\b/.test(key)) return "Investment Returns";
  if (/(^|\s)(vendor|traders)$/.test(key) || key === "carriage inward") return "Purchase";
  return "Other";
}

function newExpenseSummary_() {
  return { mtd: 0, m2: 0, m3: 0, ytd: 0 };
}

function addExpenseAmount_(summary, amount, d, ctx) {
  if (between_(d, ctx.monthStart, ctx.reportDate)) summary.mtd += amount;
  if (between_(d, ctx.last2MonthsStart, ctx.reportDate)) summary.m2 += amount;
  if (between_(d, ctx.last3MonthsStart, ctx.reportDate)) summary.m3 += amount;
  if (between_(d, ctx.fiscalYearStart, ctx.reportDate)) summary.ytd += amount;
}

function expenseCategories_() {
  return [
    "Travel Expenses", "Courier", "Office Expenses", "Salary", "Compliance Expenses",
    "Investment Returns", "Purchase", "Other", "Bank Inward", "RD"
  ];
}

function operatingExpenseCategories_() {
  return ["Travel Expenses", "Courier", "Office Expenses", "Salary", "Compliance Expenses", "Other"];
}

function paymentSummaries_(ctx) {
  if (ctx.paymentSummaries) return ctx.paymentSummaries;
  var categories = expenseCategories_();
  var monthly = {};
  var byCategory = {};
  categories.forEach(function (category) {
    monthly[category] = Array(12).fill(0);
    byCategory[category] = newExpenseSummary_();
  });
  var byAccount = {};
  var salesMonthly = Array(12).fill(0);
  var cogsMonthly = Array(12).fill(0);
  if (ctx.phase !== "expenses") {
    var sales = readTable_("sales", ["Net Amount", "Date"]);
    sales.rows.forEach(function (r) {
      var d = date_(r[sales.index.Date]);
      if (!d || d < ctx.fiscalYearStart || d > ctx.reportDate) return;
      salesMonthly[fiscalMonthIndex_(d.getMonth())] += number_(r[sales.index["Net Amount"]]);
    });
    var inventory = inventory_(ctx);
    var items = readTable_("items", ["Item Name", "Qty", "Date"]);
    items.rows.forEach(function (r) {
      var name = cleanText_(r[items.index["Item Name"]]);
      var qty = number_(r[items.index.Qty]);
      var d = date_(r[items.index.Date]);
      if (!name || !d || qty <= 0 || d < ctx.fiscalYearStart || d > ctx.reportDate) return;
      var inv = inventory[name];
      if (!inv || inv.cost === null) return;
      cogsMonthly[fiscalMonthIndex_(d.getMonth())] += qty * inv.cost;
    });
  }
  var payments = readTable_("payments", ["Date", "Account Name", "Amount"]);
  payments.rows.forEach(function (r) {
    var d = date_(r[payments.index.Date]);
    var name = cleanText_(r[payments.index["Account Name"]]);
    var amount = number_(r[payments.index.Amount]);
    if (!name || !d || d > ctx.reportDate) return;
    var category = paymentCategory_(name);
    if (!byAccount[name]) byAccount[name] = { name: name, category: category, summary: newExpenseSummary_() };
    addExpenseAmount_(byAccount[name].summary, amount, d, ctx);
    addExpenseAmount_(byCategory[category], amount, d, ctx);
    if (d >= ctx.fiscalYearStart) monthly[category][fiscalMonthIndex_(d.getMonth())] += amount;
  });
  ctx.paymentSummaries = {
    monthly: monthly,
    byCategory: byCategory,
    byAccount: byAccount,
    salesMonthly: salesMonthly,
    cogsMonthly: cogsMonthly
  };
  return ctx.paymentSummaries;
}

function monthlyLine_(label, values, reportFiscalIndex) {
  var next = values.slice();
  blankFutureFiscalValues_(next, reportFiscalIndex);
  return [label].concat(next, [sum_(next)]);
}

function inclusiveTax_(amount, rate) {
  var taxRate = Number(rate || 0);
  if (!taxRate) return 0;
  return amount * taxRate / (1 + taxRate);
}

function generateMonthlyProfitReport_(ctx) {
  var data = paymentSummaries_(ctx);
  var reportFiscalIndex = fiscalMonthIndex_(ctx.reportDate.getMonth());
  var sales = data.salesMonthly;
  var tax = sales.map(function (sale) {
    return inclusiveTax_(sale, VAY_CONFIG.salesTaxInclusiveRate);
  });
  var saleBeforeTax = sales.map(function (sale, i) { return sale - tax[i]; });
  var cogs = data.cogsMonthly;
  var investment = data.monthly["Investment Returns"];
  var operating = operatingExpenseCategories_().map(function (category) {
    return data.monthly[category];
  });
  var salesProfit = saleBeforeTax.map(function (sale, i) {
    var expenses = operating.reduce(function (sum, values) { return sum + values[i]; }, 0);
    return sale - cogs[i] - expenses - investment[i];
  });
  var rows = [
    monthlyLine_("Total Sale", sales, reportFiscalIndex),
    monthlyLine_("Tax received", tax, reportFiscalIndex),
    monthlyLine_("Sale before tax", saleBeforeTax, reportFiscalIndex),
    monthlyLine_("Less: Cost of items sold", cogs, reportFiscalIndex)
  ].concat(operatingExpenseCategories_().map(function (category) {
    return monthlyLine_("Less: " + category, data.monthly[category], reportFiscalIndex);
  })).concat([
    monthlyLine_("Less: Investment Returns", investment, reportFiscalIndex),
    monthlyLine_("Sales profit", salesProfit, reportFiscalIndex)
  ]);
  writeReport_(
    "monthly_profit_report",
    ["Component"].concat(fiscalMonthNames_(), ["Total"]),
    rows,
    null,
    { skipFormat: true, padRows: 25 }
  );
  return rows.length;
}

function generateExpenseByCategoryReport_(ctx) {
  var data = paymentSummaries_(ctx);
  var rows = expenseCategories_().map(function (category) {
    var s = data.byCategory[category];
    return [category, s.mtd, s.m2, s.m3, s.ytd];
  });
  writeReport_(
    "expense_by_category",
    ["Category", "MTD", "2 Months", "3 Months", "YTD"],
    rows,
    totalRow_(rows, 5, "Total", 1),
    { skipFormat: true }
  );
  return rows.length;
}

function generateExpenseByAccountReport_(ctx) {
  var data = paymentSummaries_(ctx);
  var rows = Object.keys(data.byAccount).map(function (name) {
    var a = data.byAccount[name];
    return [a.name, a.category, a.summary.mtd, a.summary.m2, a.summary.m3, a.summary.ytd];
  }).sort(function (a, b) { return b[5] - a[5]; });
  writeReport_(
    "expense_by_account",
    ["Account Name", "Category", "MTD", "2 Months", "3 Months", "YTD"],
    rows,
    totalRow_(rows, 6, "Total", 2),
    { skipFormat: true }
  );
  return rows.length;
}

function generateUnmappedPaymentAccounts_(ctx) {
  var data = paymentSummaries_(ctx);
  var rows = Object.keys(data.byAccount).filter(function (name) {
    return data.byAccount[name].category === "Other";
  }).map(function (name) {
    var a = data.byAccount[name];
    return [a.name, a.summary.ytd];
  }).sort(function (a, b) { return b[1] - a[1]; });
  writeReport_(
    "unmapped_payment_accounts",
    ["Account Name", "YTD Amount"],
    rows,
    rows.length ? totalRow_(rows, 2, "Total", 1) : null,
    { skipFormat: true }
  );
  return rows.length;
}

function exportSheets(dateStr) {
  return withDocumentLock_(function () {
    return exportSheetsUnlocked_(dateStr);
  });
}

function exportSheetsUnlocked_(dateStr) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var stored = PropertiesService.getDocumentProperties().getProperty("VAY_LAST_REPORT_DATE");
  var reportDate = parseReportDate_(dateStr || stored || formatDate_(new Date(), "yyyy-MM-dd"));
  var folderName = formatDate_(reportDate, "dd-MM-yyyy");
  var parent = getOrCreateFolder_(DriveApp, "vay_reports");
  var folder = getOrCreateFolder_(parent, folderName);
  var existing = {};
  var files = folder.getFiles();
  while (files.hasNext()) {
    var f = files.next();
    existing[f.getName()] = f;
  }

  var reportSheets = ss.getSheets().filter(function (sheet) {
    return isGeneratedReportSheet_(sheet.getName()) && sheet.getName() !== "report_generation_status";
  });
  var token = ScriptApp.getOAuthToken();
  var exported = 0;
  var failed = [];
  var skipped = 0;
  reportSheets.forEach(function (sheet, index) {
    var fileName = sheet.getName() + ".pdf";
    if (existing[fileName]) {
      skipped += 1;
      return;
    }
    var url = "https://docs.google.com/spreadsheets/d/" + ss.getId() + "/export" +
      "?format=pdf&gid=" + sheet.getSheetId() + "&portrait=false&size=A4&fitw=true" +
      "&top_margin=0.5&bottom_margin=0.5&left_margin=0.5&right_margin=0.5" +
      "&gridlines=false&printtitle=false&sheetnames=false&pagenumbers=true";
    try {
      var response = fetchWithRetry_(url, token, 4);
      folder.createFile(response.getBlob().setName(fileName));
      existing[fileName] = true;
      exported += 1;
    } catch (error) {
      failed.push(sheet.getName());
      Logger.log("PDF export failed for " + sheet.getName() + ": " + (error.stack || error));
    }
    Utilities.sleep(10000);
  });

  var folderUrl = folder.getUrl();
  PropertiesService.getDocumentProperties().setProperty("VAY_LAST_EXPORT_FOLDER_URL", folderUrl);
  try { updateStatusExportFolder_(folderUrl); } catch (e) { /* optional */ }
  var message = exported + " PDFs exported to vay_reports/" + folderName;
  if (skipped) message += ". " + skipped + " already existed and were skipped.";
  if (failed.length) message += " " + failed.length + " failed — run Export again after a few minutes.";
  ss.toast(message, "Vay Reports", 8);
  return {
    ok: failed.length === 0,
    count: exported,
    folderUrl: folderUrl,
    message: message
  };
}

function deleteReports() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ui = SpreadsheetApp.getUi();
  var generated = ss.getSheets().filter(function (s) { return isGeneratedReportSheet_(s.getName()); });
  var response = ui.alert(
    "Delete generated reports?",
    "This will delete " + generated.length + " generated report sheets only. Source and unrelated sheets will be kept.",
    ui.ButtonSet.YES_NO
  );
  if (response !== ui.Button.YES) return;
  withDocumentLock_(function () {
    generated.forEach(function (sheet) {
      if (ss.getSheets().length > 1) ss.deleteSheet(sheet);
    });
  });
  ss.toast(generated.length + " generated sheets deleted", "Vay Reports", 5);
}

function deleteFollowUpSheets() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var ui = SpreadsheetApp.getUi();
  var followUps = ss.getSheets().filter(function (sheet) {
    return VAY_CONFIG.followUpPrefixes.some(function (prefix) { return sheet.getName().indexOf(prefix) === 0; });
  });
  var response = ui.alert(
    "Delete follow-up sheets?",
    "This will delete " + followUps.length + " sales/collection follow-up sheets. Other reports will be kept.",
    ui.ButtonSet.YES_NO
  );
  if (response !== ui.Button.YES) return;
  withDocumentLock_(function () {
    VAY_CONFIG.followUpPrefixes.forEach(deleteSheetsWithPrefix_);
  });
  ss.toast(followUps.length + " follow-up sheets deleted", "Vay Reports", 5);
}

// -------------------- Shared helpers --------------------

function buildReportContext_(reportDate) {
  var d = normalizeDate_(reportDate);
  var monthStart = new Date(d.getFullYear(), d.getMonth(), 1, 12);
  var previousMonthStart = new Date(d.getFullYear(), d.getMonth() - 1, 1, 12);
  var previousMonthEnd = new Date(d.getFullYear(), d.getMonth(), 0, 12);
  var fyYear = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
  return {
    reportDate: d,
    timezone: spreadsheetTimeZone_(),
    accounts: null,
    inventory: null,
    monthStart: monthStart,
    previousMonthStart: previousMonthStart,
    previousMonthEnd: previousMonthEnd,
    last10Start: addDays_(d, -9),
    last15Start: addDays_(d, -14),
    last20Start: addDays_(d, -19),
    last25Start: addDays_(d, -24),
    last30Start: addDays_(d, -29),
    last60Start: addDays_(d, -59),
    last2MonthsStart: addDays_(addMonthsClamped_(d, -2), 1),
    last3MonthsStart: addDays_(addMonthsClamped_(d, -3), 1),
    fiscalYearStart: new Date(fyYear, 3, 1, 12)
  };
}

function newPeriodSummary_() {
  return { mtdSales: 0, mtdCollection: 0, d15Sales: 0, d15Collection: 0,
    m2Sales: 0, m2Collection: 0, m3Sales: 0, m3Collection: 0, ytdSales: 0, ytdCollection: 0 };
}

function addPeriodAmount_(s, type, amount, d, ctx) {
  var suffix = type === "sales" ? "Sales" : "Collection";
  if (between_(d, ctx.monthStart, ctx.reportDate)) s["mtd" + suffix] += amount;
  if (between_(d, ctx.last15Start, ctx.reportDate)) s["d15" + suffix] += amount;
  if (between_(d, ctx.last2MonthsStart, ctx.reportDate)) s["m2" + suffix] += amount;
  if (between_(d, ctx.last3MonthsStart, ctx.reportDate)) s["m3" + suffix] += amount;
  if (between_(d, ctx.fiscalYearStart, ctx.reportDate)) s["ytd" + suffix] += amount;
}

function resetRuntimeCache_() {
  VAY_SS = null;
  VAY_TABLE_CACHE = {};
  VAY_TIMEZONE = null;
  VAY_PAYMENT_MAP = null;
}

function activeSpreadsheet_() {
  if (!VAY_SS) VAY_SS = SpreadsheetApp.getActiveSpreadsheet();
  return VAY_SS;
}

function preloadSourceTables_(phase) {
  var names = ["sales", "receipt", "arr"];
  if (phase === "items" || phase === "itemprofit") names = ["items", "stock"];
  if (phase === "profit") names = ["sales", "payments", "items", "stock"];
  if (phase === "expenses") names = ["payments"];
  if (phase === "fiscal") names = ["sales", "receipt", "arr"];
  names.forEach(function (name) {
    try { readTable_(name, []); } catch (e) { /* source_data_warnings records missing sheets */ }
  });
}

function loadTableUncached_(sheetName, requiredHeaders) {
  var packed = withSpreadsheetRetry_(function () {
    var opened = activeSpreadsheet_().getSheetByName(sheetName);
    if (!opened) throw new Error("Required sheet not found: " + sheetName);
    return { sheet: opened, values: opened.getDataRange().getValues() };
  });
  var sheet = packed.sheet;
  var values = packed.values;
  if (!values.length) throw new Error("Sheet is empty: " + sheetName);
  var headers = values[0].map(function (h) { return cleanText_(h); });
  var index = {};
  headers.forEach(function (h, i) { if (h && index[h] === undefined) index[h] = i; });
  var missing = (requiredHeaders || []).filter(function (h) { return index[h] === undefined; });
  if (missing.length) throw new Error(sheetName + " is missing columns: " + missing.join(", "));
  var width = headers.length;
  var rows = values.slice(1).map(function (row) {
    var copy = row.slice();
    while (copy.length < width) copy.push("");
    return copy;
  });
  if (index.Date !== undefined) {
    rows.forEach(function (row) {
      var parsed = date_(row[index.Date]);
      if (parsed) row[index.Date] = parsed;
    });
  }
  return { sheet: sheet, sheetName: sheetName, headers: headers, index: index, rows: rows };
}

function readTable_(sheetName, requiredHeaders) {
  if (!VAY_TABLE_CACHE) VAY_TABLE_CACHE = {};
  var cached = VAY_TABLE_CACHE[sheetName];
  if (!cached) {
    cached = loadTableUncached_(sheetName, []);
    VAY_TABLE_CACHE[sheetName] = cached;
  }
  if (cached.error) throw new Error(cached.error);
  var missing = (requiredHeaders || []).filter(function (h) { return cached.index[h] === undefined; });
  if (missing.length) throw new Error(sheetName + " is missing columns: " + missing.join(", "));
  return cached;
}

function tryReadTable_(sheetName, requiredHeaders) {
  try {
    return readTable_(sheetName, requiredHeaders);
  } catch (error) {
    var fallback = { sheetName: sheetName, headers: [], index: {}, rows: [], error: error.message || String(error) };
    if (VAY_TABLE_CACHE && !VAY_TABLE_CACHE[sheetName]) VAY_TABLE_CACHE[sheetName] = fallback;
    return fallback;
  }
}

function getOrInsertSheet_(sheetName) {
  return withSpreadsheetRetry_(function () {
    return getOrInsertSheetOnce_(sheetName);
  });
}

function getOrInsertSheetOnce_(sheetName) {
  var ss = activeSpreadsheet_();
  var sheet;
  try {
    sheet = ss.getSheetByName(sheetName);
  } catch (error) {
    throw new Error("Cannot open " + sheetName + ": " + (error.message || error));
  }
  if (sheet) return sheet;
  try {
    return ss.insertSheet(sheetName);
  } catch (error) {
    throw new Error("Cannot create " + sheetName + ": " + (error.message || error));
  }
}

function writeSheetValues_(sheetName, values) {
  writeValuesToSheet_(sheetName, values);
  return getOrInsertSheet_(sheetName);
}

function writeValuesToSheet_(sheetName, values) {
  if (!values || !values.length || !values[0] || !values[0].length) return;
  var rows = values.length;
  var cols = values[0].length;
  clearSheetContentsSafe_(sheetName);
  for (var start = 0; start < rows; start += VAY_WRITE_CHUNK_ROWS) {
    var end = Math.min(start + VAY_WRITE_CHUNK_ROWS, rows);
    writeRangeValues_(sheetName, start + 1, 1, values.slice(start, end));
  }
  trimSheetLeftovers_(sheetName, rows, cols);
}

function writeRangeValues_(sheetName, startRow, startCol, values) {
  if (!values.length || !values[0].length) return;
  withSpreadsheetRetry_(function () {
    getOrInsertSheetOnce_(sheetName)
      .getRange(startRow, startCol, values.length, values[0].length)
      .setValues(values);
  });
}

function clearSheetContentsSafe_(sheetName) {
  try {
    withSpreadsheetRetry_(function () {
      var sheet = getOrInsertSheetOnce_(sheetName);
      if (sheet.getLastRow() > 0) sheet.clearContents();
    });
  } catch (error) {
    Logger.log("clearContents skipped for " + sheetName + ": " + (error.message || error));
  }
}

function trimSheetLeftovers_(sheetName, rows, cols) {
  try {
    withSpreadsheetRetry_(function () {
      var sheet = getOrInsertSheetOnce_(sheetName);
      var lastRow = sheet.getLastRow();
      var lastCol = sheet.getLastColumn();
      if (lastRow > rows) {
        sheet.getRange(rows + 1, 1, lastRow - rows, Math.max(lastCol, cols)).clearContent();
      }
      lastCol = sheet.getLastColumn();
      if (lastCol > cols && rows > 0) {
        sheet.getRange(1, cols + 1, rows, lastCol - cols).clearContent();
      }
    });
  } catch (error) {
    Logger.log("trim leftovers skipped for " + sheetName + ": " + (error.message || error));
  }
}

function writeReport_(sheetName, headers, rows, totalRow, options) {
  options = options || {};
  var output = [headers];
  if (rows && rows.length) {
    for (var i = 0; i < rows.length; i++) output.push(rows[i]);
  }
  if (totalRow) output.push(totalRow);
  if (options.padRows) {
    var width = headers.length;
    while (output.length < options.padRows) output.push(Array(width).fill(""));
  }
  var sheet = writeSheetValues_(sheetName, output);
  if (!options.skipFormat) {
    try {
      sheet.getRange(1, 1, 1, headers.length).setFontWeight("bold");
      sheet.setFrozenRows(1);
    } catch (e) { /* values already written */ }
  }
  if (options.statusHeader && rows && rows.length) {
    try { colorStatusColumnFromRows_(sheet, headers, options.statusHeader, rows); } catch (e) { /* values already written */ }
  }
  return rows ? rows.length : 0;
}

function applyColumnFormatsFast_(sheet, headers, rowCount) {
  if (headers.length < 2 || rowCount < 2) return;
  var textHeaders = {};
  VAY_CONFIG.textHeaders.forEach(function (h) { textHeaders[h] = true; });
  var start = -1;
  for (var c = 0; c <= headers.length; c++) {
    var isText = c === headers.length || c === 0 || textHeaders[headers[c]];
    if (!isText) {
      if (start < 0) start = c;
    } else if (start >= 0) {
      sheet.getRange(2, start + 1, rowCount - 1, c - start).setNumberFormat("#,##0.00");
      start = -1;
    }
  }
}

function colorStatusColumnFromRows_(sheet, headers, headerName, rows) {
  var col = headers.indexOf(headerName);
  if (col < 0 || !rows || !rows.length) return;
  var backgrounds = rows.map(function (row) {
    return [VAY_CONFIG.statusColors[row[col]] || "#ffffff"];
  });
  sheet.getRange(2, col + 1, rows.length, 1).setBackgrounds(backgrounds);
}

function colorStatusColumn_(sheet, headers, headerName, dataRowCount) {
  var col = headers.indexOf(headerName);
  if (col < 0 || dataRowCount < 1) return;
  var values = sheet.getRange(2, col + 1, dataRowCount, 1).getValues();
  colorStatusColumnFromRows_(sheet, headers, headerName, values);
}

function writeGenerationStatus_(ctx, statuses, durationMs, exportFolderUrl) {
  try {
    var values = [
      ["Generated At", "Report Date", "Timezone", "Duration (s)", "Phase", "Export Folder"],
      [
        formatDate_(new Date(), "yyyy-MM-dd HH:mm:ss"),
        formatDate_(ctx.reportDate, "yyyy-MM-dd"),
        ctx.timezone,
        (Number(durationMs || 0) / 1000).toFixed(1),
        ctx.phase || "core",
        exportFolderUrl || ""
      ],
      ["", "", "", "", "", ""],
      ["Report", "Status", "Rows", "Message"]
    ];
    (statuses || []).forEach(function (row) { values.push(row); });
    writeSheetValues_("report_generation_status", values);
    return statuses ? statuses.length : 0;
  } catch (error) {
    Logger.log("report_generation_status write skipped: " + (error.stack || error));
    return 0;
  }
}

function updateStatusExportFolder_(url) {
  try {
    var sheet = activeSpreadsheet_().getSheetByName("report_generation_status");
    if (!sheet || sheet.getLastRow() < 2) return;
    var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
    var index = headers.indexOf("Export Folder");
    if (index >= 0) sheet.getRange(2, index + 1).setValue(url);
  } catch (e) { /* export folder link is optional */ }
}

function stockMap_() {
  var stock = readTable_("stock", ["Item Name", "Qty", "P.Price"]);
  var map = {};
  stock.rows.forEach(function (r) {
    var name = cleanText_(r[stock.index["Item Name"]]);
    if (!name) return;
    var qty = number_(r[stock.index.Qty]);
    var rawCost = r[stock.index["P.Price"]];
    var parsedCost = parseFloat(String(rawCost).replace(/,/g, ""));
    if (!map[name]) map[name] = { qty: 0, value: 0, pricedQty: 0, fallbackCost: null, cost: null };
    map[name].qty += qty;
    if (!isNaN(parsedCost)) {
      map[name].fallbackCost = parsedCost;
      if (qty > 0) { map[name].value += qty * parsedCost; map[name].pricedQty += qty; }
    }
  });
  Object.keys(map).forEach(function (name) {
    map[name].cost = map[name].pricedQty > 0 ? map[name].value / map[name].pricedQty : map[name].fallbackCost;
  });
  return map;
}

function inventory_(ctx) {
  if (!ctx.inventory) ctx.inventory = stockMap_();
  return ctx.inventory;
}

function requireAccounts_(ctx) {
  if (!ctx.accounts) throw new Error("Account performance data is not available");
}

function estimateAgeing_(balance, salesBucketsNewestFirst) {
  var remaining = balance;
  var allocated = salesBucketsNewestFirst.map(function (sales) {
    var amount = Math.min(remaining, Math.max(0, sales));
    remaining -= amount;
    return amount;
  });
  allocated[3] += Math.max(0, remaining);
  return allocated;
}

function totalRow_(rows, width, label, numericStart) {
  var total = Array(width).fill(0);
  total[0] = label;
  for (var c = numericStart; c < width; c++) {
    total[c] = rows.reduce(function (sum, row) { return sum + number_(row[c]); }, 0);
  }
  for (var i = 1; i < numericStart; i++) total[i] = "";
  return total;
}

function rewriteSourceSheet_(sheetName, mutator) {
  var table = loadTableUncached_(sheetName, []);
  var headers = table.headers.slice();
  var rows = table.rows.map(function (r) { return r.slice(); });
  var next = mutator(headers, indexFromHeaders_(headers), rows) || rows;
  var width = headers.length;
  next.forEach(function (row) {
    while (row.length < width) row.push("");
  });
  var output = [headers].concat(next);
  writeValuesToSheet_(sheetName, output);
  var index = indexFromHeaders_(headers);
  return { message: sheetName + ": " + next.length + " rows", rows: next, index: index, headers: headers };
}

function indexFromHeaders_(headers) {
  var index = {};
  headers.forEach(function (h, i) { if (h && index[h] === undefined) index[h] = i; });
  return index;
}

function dropExactTotalRows_(rows, columnIndex) {
  if (columnIndex === undefined) return rows;
  return rows.filter(function (row) { return cleanText_(row[columnIndex]).toLowerCase() !== "total"; });
}

function fillBlankInRows_(rows, columnIndex, defaultValue) {
  if (columnIndex === undefined) return;
  rows.forEach(function (row) {
    var v = row[columnIndex];
    if (v === "" || v === null || v === undefined) row[columnIndex] = defaultValue;
  });
}

function normalizeDateInRows_(rows, columnIndex) {
  if (columnIndex === undefined) return;
  rows.forEach(function (row) {
    var d = date_(row[columnIndex]);
    if (d) row[columnIndex] = d;
  });
}

function rowsHaveValue_(rows, columnIndex, value) {
  if (columnIndex === undefined) return false;
  return rows.some(function (row) { return cleanText_(row[columnIndex]) === value; });
}

function writeFollowUpGroupSheets_(prefix, groups, headers, options) {
  var totalRows = 0;
  Object.keys(groups).forEach(function (group) {
    var name = safeSheetName_(prefix + group);
    writeReport_(name, headers, groups[group], null, options);
    totalRows += groups[group].length;
  });
  return totalRows;
}

function deleteUnusedFollowUpSheets_(prefix, keepNames) {
  var ss = activeSpreadsheet_();
  ss.getSheets().forEach(function (sheet) {
    var name = sheet.getName();
    if (name.indexOf(prefix) !== 0 || keepNames[name]) return;
    if (ss.getSheets().length <= 1) return;
    ss.deleteSheet(sheet);
  });
}

function itemSummaries_(ctx) {
  if (ctx.itemSummaries) return ctx.itemSummaries;
  var items = readTable_("items", ["Item Name", "Qty", "Rate", "Date"]);
  var inventory = inventory_(ctx);
  var reportFiscalIndex = fiscalMonthIndex_(ctx.reportDate.getMonth());
  var recentStart = new Date(ctx.reportDate.getFullYear(), ctx.reportDate.getMonth() - 3, 1, 12);
  var sales = {};
  var profit = {};
  var missing = {};
  var monthlyProfit = {};
  var monthlyQty = {};

  items.rows.forEach(function (r) {
    var name = cleanText_(r[items.index["Item Name"]]);
    var qty = number_(r[items.index.Qty]);
    var rate = number_(r[items.index.Rate]);
    var d = date_(r[items.index.Date]);
    if (!name || !d || qty <= 0 || d > ctx.reportDate) return;

    var inFiscalYear = between_(d, ctx.fiscalYearStart, ctx.reportDate);
    var inRecentCompletedMonths = between_(d, recentStart, ctx.previousMonthEnd);
    if (inFiscalYear || inRecentCompletedMonths) {
      if (!monthlyQty[name]) monthlyQty[name] = { monthly: Array(12).fill(0), recentQty: 0 };
      if (inFiscalYear) monthlyQty[name].monthly[fiscalMonthIndex_(d.getMonth())] += qty;
      if (inRecentCompletedMonths) monthlyQty[name].recentQty += qty;
    }

    if (rate < 0) return;
    if (!sales[name]) sales[name] = { mtdQty: 0, mtd: 0, lastMonth: 0, m3: 0, ytd: 0 };
    var amount = qty * rate;
    if (between_(d, ctx.monthStart, ctx.reportDate)) { sales[name].mtdQty += qty; sales[name].mtd += amount; }
    if (between_(d, ctx.previousMonthStart, ctx.previousMonthEnd)) sales[name].lastMonth += amount;
    if (between_(d, ctx.last3MonthsStart, ctx.reportDate)) sales[name].m3 += amount;
    if (inFiscalYear) sales[name].ytd += amount;

    if (!Object.prototype.hasOwnProperty.call(inventory, name) || inventory[name].cost === null) {
      missing[name] = "Missing valid P.Price in stock";
      return;
    }
    if (ctx.phase !== "itemprofit") return;
    var profitAmount = (rate - inventory[name].cost) * qty;
    if (!profit[name]) profit[name] = { mtdQty: 0, mtd: 0, lastMonth: 0, m3: 0, ytd: 0 };
    if (between_(d, ctx.monthStart, ctx.reportDate)) { profit[name].mtdQty += qty; profit[name].mtd += profitAmount; }
    if (between_(d, ctx.previousMonthStart, ctx.previousMonthEnd)) profit[name].lastMonth += profitAmount;
    if (between_(d, ctx.last3MonthsStart, ctx.reportDate)) profit[name].m3 += profitAmount;
    if (inFiscalYear) {
      profit[name].ytd += profitAmount;
      if (!monthlyProfit[name]) monthlyProfit[name] = Array(12).fill(0);
      monthlyProfit[name][fiscalMonthIndex_(d.getMonth())] += profitAmount;
    }
  });

  var salesRows = Object.keys(sales).map(function (name) {
    var s = sales[name]; return [name, s.mtdQty, s.mtd, s.lastMonth, s.m3, s.ytd];
  }).sort(function (a, b) { return b[5] - a[5]; });

  var profitRows = Object.keys(profit).map(function (name) {
    var s = profit[name]; return [name, s.mtdQty, s.mtd, s.lastMonth, s.m3, s.ytd];
  }).sort(function (a, b) { return b[5] - a[5]; });

  var monthlyProfitRows = Object.keys(monthlyProfit).map(function (name) {
    var values = monthlyProfit[name].slice();
    var total = sum_(values);
    blankFutureFiscalValues_(values, reportFiscalIndex);
    return [name].concat(values, [total]);
  }).sort(function (a, b) { return b[13] - a[13]; });
  var monthlyProfitTotal = totalRow_(monthlyProfitRows, 14, "Total", 1);
  for (var i = 0; i < 12; i++) {
    if (i > reportFiscalIndex) monthlyProfitTotal[i + 1] = "";
  }

  var monthlyQtyRows = Object.keys(monthlyQty).map(function (name) {
    var values = monthlyQty[name].monthly.slice();
    var average = monthlyQty[name].recentQty / 3;
    var stock = inventory[name] ? inventory[name].qty : 0;
    var status = "OK";
    if (average > 0 && stock > average) status = "EXCESS STOCK";
    else if (average > 0 && stock < average) status = "LOW STOCK";
    var total = sum_(values);
    blankFutureFiscalValues_(values, reportFiscalIndex);
    return [name].concat(values, [average, total, stock, status]);
  }).sort(function (a, b) { return b[14] - a[14]; });

  ctx.itemSummaries = {
    salesRows: salesRows,
    profitRows: profitRows,
    missingRows: Object.keys(missing).map(function (n) { return [n, missing[n]]; }),
    monthlyProfitRows: monthlyProfitRows,
    monthlyProfitTotal: monthlyProfitTotal,
    monthlyQtyRows: monthlyQtyRows
  };
  return ctx.itemSummaries;
}

function deleteSheetsWithPrefix_(prefix) {
  deleteUnusedFollowUpSheets_(prefix, {});
}

function isGeneratedReportSheet_(name) {
  if (VAY_CONFIG.fixedReportSheets.indexOf(name) >= 0) return true;
  return VAY_CONFIG.followUpPrefixes.some(function (prefix) { return name.indexOf(prefix) === 0; });
}

function safeSheetName_(name) {
  var cleaned = String(name).replace(/[\\\/\?\*\[\]:]/g, "-").substring(0, 100);
  return cleaned || "report";
}

function fetchWithRetry_(url, token, attempts) {
  var lastError;
  for (var i = 0; i < attempts; i++) {
    try {
      var response = UrlFetchApp.fetch(url, { headers: { Authorization: "Bearer " + token }, muteHttpExceptions: true });
      var code = response.getResponseCode();
      if (code >= 200 && code < 300) return response;
      lastError = new Error("PDF export returned HTTP " + code);
      if (code === 429 && i < attempts - 1) {
        Utilities.sleep([5000, 15000, 30000][Math.min(i, 2)]);
        continue;
      }
    } catch (e) { lastError = e; }
    if (i < attempts - 1) Utilities.sleep(Math.pow(2, i) * 1000);
  }
  throw lastError;
}

function getOrCreateFolder_(parent, name) {
  var folders = parent.getFoldersByName(name);
  return folders.hasNext() ? folders.next() : parent.createFolder(name);
}

function parseReportDate_(value) {
  var text = String(value || "").trim();
  var match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text);
  if (!match) throw new Error("Invalid report date. Use YYYY-MM-DD.");
  var d = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12);
  if (d.getFullYear() !== Number(match[1]) || d.getMonth() !== Number(match[2]) - 1 || d.getDate() !== Number(match[3])) {
    throw new Error("Invalid report date: " + text);
  }
  return d;
}

function date_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) return normalizeDate_(value);
  if (value === null || value === undefined || value === "") return null;
  var text = String(value).trim();
  var m = /^(\d{1,2})[-\/]([0-9]{1,2})[-\/]([0-9]{2}|[0-9]{4})$/.exec(text);
  if (m) {
    var year = Number(m[3]); if (year < 100) year += 2000;
    var dmy = new Date(year, Number(m[2]) - 1, Number(m[1]), 12);
    return isNaN(dmy.getTime()) ? null : dmy;
  }
  var iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  if (iso) {
    var ymd = new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]), 12);
    return isNaN(ymd.getTime()) ? null : ymd;
  }
  var parsed = new Date(value);
  return isNaN(parsed.getTime()) ? null : normalizeDate_(parsed);
}

function normalizeDate_(d) { return new Date(d.getFullYear(), d.getMonth(), d.getDate(), 12); }
function between_(d, start, end) { return d >= start && d <= end; }
function addDays_(d, days) { var result = new Date(d); result.setDate(result.getDate() + days); return normalizeDate_(result); }
function addMonthsClamped_(d, months) {
  var targetMonth = d.getMonth() + months;
  var result = new Date(d.getFullYear(), targetMonth, 1, 12);
  var lastDay = new Date(result.getFullYear(), result.getMonth() + 1, 0, 12).getDate();
  result.setDate(Math.min(d.getDate(), lastDay));
  return result;
}
function fiscalMonthIndex_(calendarMonth) { return (calendarMonth + 9) % 12; }
function fiscalMonthNames_() { return ["April", "May", "June", "July", "August", "September", "October", "November", "December", "January", "February", "March"]; }
function fiscalMonths_(start) { return Array.from({ length: 12 }, function (_, i) { return new Date(start.getFullYear(), start.getMonth() + i, 1, 12); }); }

function blankFutureFiscalValues_(values, reportFiscalIndex) {
  for (var i = reportFiscalIndex + 1; i < values.length; i++) values[i] = "";
}

function blankFutureFiscalPairs_(values, reportFiscalIndex) {
  for (var i = reportFiscalIndex + 1; i < 12; i++) {
    values[i * 2] = "";
    values[i * 2 + 1] = "";
  }
}

function blankFutureFiscalMonthRow_(row, reportFiscalIndex, offset) {
  for (var i = reportFiscalIndex + 1; i < 12; i++) {
    row[offset + i * 2] = "";
    row[offset + i * 2 + 1] = "";
  }
}

function addCountWarning_(warnings, map, type, source, suffix) {
  var keys = Object.keys(map);
  var limit = 50;
  keys.slice(0, limit).forEach(function (key) {
    warnings.push([type, source, map[key].name, map[key].count + " " + suffix]);
  });
  if (keys.length > limit) {
    warnings.push([type, source, "", (keys.length - limit) + " more " + suffix]);
  }
}

function addSummaryWarning_(warnings, type, source, count, detail) {
  if (count > 0) warnings.push([type, source, "", count + " " + detail]);
}

function fiscalTaskNames_() {
  return [
    "Fiscal monthly group performance",
    "Fiscal monthly sales and collection",
    "Fiscal monthly account performance"
  ];
}

function loadFiscalProgress_(reportDate) {
  var dateLabel = formatDate_(reportDate, "yyyy-MM-dd");
  var progress = { date: dateLabel, done: {} };
  try {
    var raw = PropertiesService.getDocumentProperties().getProperty("VAY_FISCAL_PROGRESS");
    if (raw) {
      var parsed = JSON.parse(raw);
      if (parsed && parsed.date === dateLabel && parsed.done) progress = parsed;
    }
  } catch (e) { /* start a fresh fiscal run */ }
  var names = fiscalTaskNames_();
  var complete = names.every(function (name) { return progress.done[name]; });
  if (complete) progress.done = {};
  return progress;
}

function saveFiscalProgress_(progress) {
  try {
    PropertiesService.getDocumentProperties().setProperty("VAY_FISCAL_PROGRESS", JSON.stringify(progress));
  } catch (e) { /* retry still works if this run wrote one sheet */ }
}

function isSpreadsheetTimeout_(error) {
  return /timed out/i.test(String(error && error.message || error || ""));
}

function isSpreadsheetRetryable_(error) {
  var msg = String(error && error.message || error || "");
  return /timed out|service error|internal error|unavailable|rate limit|too many|backend error|try again|502|503|429/i.test(msg);
}

function withSpreadsheetRetry_(fn) {
  var delay = VAY_SHEETS_RETRY_MS;
  var lastError;
  for (var i = 0; i < VAY_SHEETS_RETRIES; i++) {
    try {
      return fn();
    } catch (error) {
      lastError = error;
      if (!isSpreadsheetRetryable_(error) || i === VAY_SHEETS_RETRIES - 1) throw error;
      Logger.log("Spreadsheet retry " + (i + 1) + "/" + (VAY_SHEETS_RETRIES - 1) + " in " + delay + "ms: " + (error.message || error));
      Utilities.sleep(delay);
      delay = Math.min(delay * 2, 16000);
      VAY_SS = null;
    }
  }
  throw lastError;
}

function isProfitTaskPhase_(phase) {
  return phase === "profit" || phase === "expenses" || phase === "itemprofit";
}

function taskShouldRun_(task, phase) {
  if (isProfitTaskPhase_(task.phase) && !isProfitTaskPhase_(phase)) return false;
  if (task.phase === "always") return phase === "core" || phase === "items";
  return task.phase === phase;
}

function passwordHash_(value) {
  var digest = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(value || ""), Utilities.Charset.UTF_8);
  return digest.map(function (byte) {
    var hex = (byte < 0 ? byte + 256 : byte).toString(16);
    return hex.length === 1 ? "0" + hex : hex;
  }).join("");
}

function requireProfitPassword_() {
  var ui = SpreadsheetApp.getUi();
  var response = ui.prompt("Profit reports", "Enter password", ui.ButtonSet.OK_CANCEL);
  if (response.getSelectedButton() !== ui.Button.OK) return false;
  return passwordHash_(response.getResponseText()) === VAY_CONFIG.profitPasswordSha256;
}

function normalizePhase_(phase) {
  var value = cleanText_(phase).toLowerCase();
  return value === "core" || value === "fiscal" || value === "items" || value === "profit" || value === "expenses" || value === "itemprofit" ? value : "core";
}

function promptReportDate_() {
  var ui = SpreadsheetApp.getUi();
  var defaultDate = formatDate_(new Date(), "yyyy-MM-dd");
  var response = ui.prompt(
    "Generate Vay Reports",
    "Enter report date as YYYY-MM-DD (default " + defaultDate + ")",
    ui.ButtonSet.OK_CANCEL
  );
  if (response.getSelectedButton() !== ui.Button.OK) return null;
  return String(response.getResponseText() || defaultDate).trim();
}

function withDocumentLock_(fn) {
  var lock = LockService.getDocumentLock();
  if (!lock.tryLock(30000)) {
    throw new Error("Another Vay Reports run is in progress. Try again shortly.");
  }
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

function spreadsheetTimeZone_() {
  if (VAY_TIMEZONE) return VAY_TIMEZONE;
  try {
    VAY_TIMEZONE = Session.getScriptTimeZone() || "Asia/Kolkata";
  } catch (e) {
    VAY_TIMEZONE = "Asia/Kolkata";
  }
  return VAY_TIMEZONE;
}

function number_(value) {
  if (value === "" || value === null || value === undefined) return 0;
  var n = parseFloat(String(value).replace(/,/g, ""));
  return isNaN(n) ? 0 : n;
}
function cleanText_(value) { return value === null || value === undefined ? "" : String(value).trim(); }
function sum_(values) { return values.reduce(function (sum, value) { return sum + number_(value); }, 0); }
function formatDate_(date, pattern) { return Utilities.formatDate(date, VAY_TIMEZONE || spreadsheetTimeZone_(), pattern); }
