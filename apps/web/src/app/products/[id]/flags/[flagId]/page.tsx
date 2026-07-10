// meta: U7 flag detail route (07 §4). M0 stub; highlighted evidence, verdict
// tags, lifecycle strip, disposition panel, why-flagged chain land at M5.
export default async function FlagDetailPage({
  params,
}: {
  params: Promise<{ id: string; flagId: string }>;
}) {
  const { id, flagId } = await params;
  return (
    <main className="p-8">
      <p className="text-sm text-muted-foreground">
        Flag {flagId} of product {id} (M5)
      </p>
    </main>
  );
}
