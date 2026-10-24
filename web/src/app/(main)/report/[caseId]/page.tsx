// F-M1.2–F-M1.10 Reporter / island clinician case page
import ReportCaseClient from "./ReportCaseClient";

export const metadata = { title: "Case" };

export default async function ({ params }: PageProps<"/report/[caseId]">) {
  const { caseId } = await params;
  return <ReportCaseClient caseId={caseId} />;
}
