// meta: U6 product detail route (07 §4). M0 stub; metric row + flags list
// (both groupings) + disposition land at M5.
export default async function ProductDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return (
    <main className="p-8">
      <p className="text-sm text-muted-foreground">Product {id} (M5)</p>
    </main>
  );
}
