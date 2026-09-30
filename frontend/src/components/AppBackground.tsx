/** Decorative ambient background — no interaction, aria-hidden. */
export default function AppBackground() {
  return (
    <div className="ambient-bg" aria-hidden>
      <div className="orb orb-1" />
      <div className="orb orb-2" />
      <div className="orb orb-3" />
      <div className="grid-glow" />
    </div>
  );
}
