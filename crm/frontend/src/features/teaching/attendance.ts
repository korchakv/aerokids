export type AttendanceValue = "present" | "absent" | "late" | "excused";

export function attendanceStatusLabel(value: AttendanceValue | undefined) {
  const labels: Record<AttendanceValue, string> = {
    present: "Був",
    absent: "Не був",
    excused: "Поважна причина",
    late: "Запізнився",
  };
  return value ? labels[value] : "Не відмічено";
}
