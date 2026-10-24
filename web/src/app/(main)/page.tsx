import { redirect } from "next/navigation";

// AtollCare opens straight into the crew experience.
export default async function () {
  redirect("/crew");
}
