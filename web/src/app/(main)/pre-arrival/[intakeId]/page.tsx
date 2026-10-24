import PreArrivalClient from "./PreArrivalClient";

export const metadata = { title: "Before you arrive" };

export default async function ({ params }: PageProps<"/pre-arrival/[intakeId]">) {
  const { intakeId } = await params;
  return <PreArrivalClient intakeId={intakeId} />;
}
