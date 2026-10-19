import AdvancedSection from "./settings/AdvancedSection";
import AuditSection from "./settings/AuditSection";
import AccountNamesSection from "./settings/AccountNamesSection";
import NameReviewSection from "./settings/NameReviewSection";
import DueDaysSection from "./settings/DueDaysSection";
import NetworkSection from "./settings/NetworkSection";
import OrderCheckDefaultsSection from "./settings/OrderCheckDefaultsSection";
import LicenseSection from "./settings/LicenseSection";
import OrganizationSection from "./settings/OrganizationSection";
import PartyTypesSection from "./settings/PartyTypesSection";
import RolesSection from "./settings/RolesSection";
import SettlementSection from "./settings/SettlementSection";
import UsersSection from "./settings/UsersSection";
import SectionTabs from "./SectionTabs";

export default function SettingsPage({ section, tabs, selected, onSection, storageKey, user, onFactoryReset, onSnapshotsCleared }) {
  const body = settingsBody(section, user, onFactoryReset, onSnapshotsCleared);
  return (
    <div className="stack">
      {tabs?.length ? <SectionTabs label="Settings" storageKey={storageKey} tabs={tabs} value={selected || section} onChange={onSection} /> : null}
      {body}
    </div>
  );
}

function settingsBody(section, user, onFactoryReset, onSnapshotsCleared) {
  if (section === "network") return <NetworkSection />;
  if (section === "organization") return <OrganizationSection />;
  if (section === "license") return <LicenseSection />;
  if (section === "account-names") {
    return (
      <div className="stack">
        <AccountNamesSection />
        <NameReviewSection />
      </div>
    );
  }
  if (section === "users") return <UsersSection user={user} />;
  if (section === "roles") return <RolesSection user={user} />;
  if (section === "settlement") return <SettlementSection />;
  if (section === "due-days") return <DueDaysSection />;
  if (section === "order-check") return <OrderCheckDefaultsSection />;
  if (section === "party-types") return <PartyTypesSection />;
  if (section === "audit") return <AuditSection />;
  if (section === "advanced") return <AdvancedSection onFactoryReset={onFactoryReset} onSnapshotsCleared={onSnapshotsCleared} />;
  return <p className="muted">That page is not available for this account.</p>;
}
