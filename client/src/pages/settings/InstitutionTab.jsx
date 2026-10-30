import InstitutionSettings from "../../components/admin/InstitutionSettings";
import { Card, CardHeader } from "../../components/ui";

/** Admins only (guarded in App.jsx). */
const InstitutionTab = () => (
  <Card className="max-w-3xl">
    <CardHeader
      title="Institution"
      description="Your logo and name lead every page for everyone in your institution, with Cohortix in the background."
    />
    <InstitutionSettings />
  </Card>
);

export default InstitutionTab;
