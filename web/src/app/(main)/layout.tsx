import Footer from "@/app/components/Footer";
import Header from "@/app/components/Header";
import Toaster from "@/app/components/Toaster";

export default function ({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="mx-auto w-full max-w-[90rem] flex-1 px-[1rem] pb-[2rem] pt-[4.5rem]">{children}</main>
      <Footer />
      <Toaster />
    </>
  );
}
