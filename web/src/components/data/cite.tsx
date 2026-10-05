/**
 * A numbered citation in story prose: the number links to the story's source list entry, which links to the source
 * page. Numbers follow the order of the story's `sources` (bound per page in the story template).
 */
export function makeCite(order: string[]) {
  return function Cite({ id }: { id: string }) {
    const n = order.indexOf(id);
    if (n < 0) throw new Error(`<Cite id="${id}"> is not in this story's sources: ${order.join(", ")}`);
    return (
      <sup className="ml-0.5">
        <a href={`#source-${id}`} className="text-link no-underline hover:underline" aria-label={`Source ${n + 1}`} data-cite={id}>
          [{n + 1}]
        </a>
      </sup>
    );
  };
}
