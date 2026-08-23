"use client";

import { use, useEffect } from "react";
import { useRouter } from "next/navigation";

export default function ResultsRedirectPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const router = useRouter();

  useEffect(() => {
    if (sessionId) {
      router.replace(`/?session=${encodeURIComponent(sessionId)}`);
    }
  }, [sessionId, router]);

  return null;
}
