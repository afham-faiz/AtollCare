// F-M8.1 reset · F-M8.2 world controls · F-M8.3 scenarios · F-M8.4 presenter view (?view=split)
import DemoClient from "./DemoClient";

export const metadata = { title: "Demo control" };

export default async function ({ searchParams }: PageProps<"/demo">) {
  const sp = await searchParams;
  return <DemoClient split={sp.view === "split"} />;
}
