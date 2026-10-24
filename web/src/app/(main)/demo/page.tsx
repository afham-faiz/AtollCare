import PresenterTools from "@/app/components/(shell)/PresenterTools";

export const metadata = { title: "Presenter" };

// Full-page version of the presenter tools (also available anywhere with Ctrl + .).
export default async function () {
  return (
    <div className="mx-auto w-full max-w-[34rem]">
      <h1 className="mb-[1rem] text-[1.5rem] font-[650] tracking-[-0.02em]">Presenter</h1>
      <PresenterTools />
    </div>
  );
}
