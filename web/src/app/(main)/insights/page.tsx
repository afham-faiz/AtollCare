import InsightsClient from "./InsightsClient";

export const metadata = { title: "Network insights" };

export default async function () {
  return <InsightsClient />;
}
