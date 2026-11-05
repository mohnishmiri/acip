import ResourceDetailPage from "@/features/resources/ResourceDetailPage";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResourceDetailPage id={id} />;
}
