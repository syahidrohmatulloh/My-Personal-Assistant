import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { HomeCommandCenterClient } from "./home-command-center-client";

export default async function HomeCommandCenterPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return <HomeCommandCenterClient />;
}
