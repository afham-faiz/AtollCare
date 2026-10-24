// F-M3.2 Case review · F-M3.3 Accept/Decline/Request info · F-M3.4 Q&A · F-M3.6 notes · F-M3.7 close · F-M3.9
import HospitalCaseClient from "./HospitalCaseClient";

export const metadata = { title: "Case review" };

export default async function ({ params }: PageProps<"/hospital/[caseId]">) {
  const { caseId } = await params;
  return <HospitalCaseClient caseId={caseId} />;
}
