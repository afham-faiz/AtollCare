import PresenterPanel from "@/app/components/(shell)/PresenterPanel";
import TopBar from "@/app/components/(shell)/TopBar";
import Toaster from "@/app/components/Toaster";

export default function ({ children }: { children: React.ReactNode }) {
  return (
    <>
      <TopBar />
      <main className="mx-auto flex w-full max-w-[96rem] flex-1 flex-col px-[1.5rem] pb-[2rem] pt-[1.5rem] max-sm:px-[1rem]">
        {children}
      </main>
      <PresenterPanel />
      <Toaster />
    </>
  );
}
