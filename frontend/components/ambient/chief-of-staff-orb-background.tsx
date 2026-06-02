"use client";

export function ChiefOfStaffOrbBackground() {
  return (
    <div
      aria-hidden="true"
      data-background-style="chief-of-staff-orb"
      className="chief-staff-orb-background"
    >
      <div className="chief-staff-grid" />
      <div className="chief-staff-orb-shell">
        <span className="chief-staff-orb-ring chief-staff-orb-ring-a" />
        <span className="chief-staff-orb-ring chief-staff-orb-ring-b" />
        <span className="chief-staff-orb-ring chief-staff-orb-ring-c" />
        <span className="chief-staff-orb-core" />
        <span className="chief-staff-orb-scanline" />
      </div>
      <div className="chief-staff-orb-vignette" />
    </div>
  );
}
