import AdvancedSection from "./settings/AdvancedSection";
import AuditSection from "./settings/AuditSection";
import AccountNamesSection from "./settings/AccountNamesSection";
import NameReviewSection from "./settings/NameReviewSection";
import DueDaysSection from "./settings/DueDaysSection";
import NetworkSection from "./settings/NetworkSection";
import OrderCheckDefaultsSection from "./settings/OrderCheckDefaultsSection";
import OrganizationSection from "./settings/OrganizationSection";
import PartyTypesSection from "./settings/PartyTypesSection";
import RolesSection from "./settings/RolesSection";
import SettlementSection from "./settings/SettlementSection";
import UsersSection from "./settings/UsersSection";

export default function SettingsPage({ section, user, onFactoryReset }) {
  if (section === "network") return <NetworkSection />;
  if (section === "organization") return <OrganizationSection />;
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
  return <AdvancedSection onFactoryReset={onFactoryReset} />;
}
