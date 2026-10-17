import { Card, PageHeader } from "../../components/ui";
import StudentsTable from "../../components/StudentsTable";

const Students = () => (
  <div className="space-y-6">
    <PageHeader
      eyebrow="Teaching"
      title="My students"
      description="Every student in your institution with their practice activity over the last 90 days."
    />
    <Card>
      <StudentsTable />
    </Card>
  </div>
);

export default Students;
