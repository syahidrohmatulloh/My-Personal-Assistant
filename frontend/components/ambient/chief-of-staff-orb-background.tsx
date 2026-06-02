"use client";

export function ChiefOfStaffOrbBackground() {
  return (
    <div
      aria-hidden="true"
      data-background-style="chief-of-staff-orb"
      className="ambient-background ambient-intensity-low ambient-palette-focus-cyan chief-staff-orb-background"
    >
      <span className="ambient-layer ambient-layer-a chief-staff-theme-layer chief-staff-theme-layer-a" />
      <span className="ambient-layer ambient-layer-b chief-staff-theme-layer chief-staff-theme-layer-b" />
      <span className="ambient-layer ambient-layer-c chief-staff-theme-layer chief-staff-theme-layer-c" />

      <div className="chief-staff-orb-shell">
        <span className="chief-staff-orb-ring chief-staff-orb-ring-a" />
        <span className="chief-staff-orb-ring chief-staff-orb-ring-b" />
        <span className="chief-staff-orb-ring chief-staff-orb-ring-c" />
        <span className="chief-staff-orb-core" />
        <span className="chief-staff-orb-scanline" />
      </div>

      <span className="ambient-readability-vignette chief-staff-orb-vignette" />
    </div>
  );
}
