export type AvailabilitySlot = {
  weekday: number;
  start_time: string;
  end_time: string;
  preference: "preferred" | "possible" | "avoid";
  note?: string | null;
};

export type AvailabilityWindowDraft = {
  id: string;
  weekdays: number[];
  start_time: string;
  end_time: string;
  preference: AvailabilitySlot["preference"];
  note?: string | null;
};

export type DraftScheduleSlot = { weekday: number; start_time: string; duration_minutes: number };


export const DAY_NAMES = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"];
export const TIME_OPTIONS = Array.from({ length: 56 }, (_, index) => `${String(8 + Math.floor(index / 4)).padStart(2, "0")}:${String((index % 4) * 15).padStart(2, "0")}`);

export function TimeSelect({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label>{label}<select value={value.slice(0, 5)} onChange={(event) => onChange(event.target.value)}>{TIME_OPTIONS.map((time) => <option key={time}>{time}</option>)}</select></label>;
}

export function WeekdayPicker({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <label>День<select value={value} onChange={(event) => onChange(Number(event.target.value))}>{DAY_NAMES.map((day, index) => <option value={index} key={day}>{day}</option>)}</select></label>;
}

export function DurationSelect({ value, onChange }: { value: number; onChange: (value: number) => void }) {
  return <label>Тривалість<select value={value} onChange={(event) => onChange(Number(event.target.value))}>{[45, 60, 75, 90].map((minutes) => <option value={minutes} key={minutes}>{minutes} хв</option>)}</select></label>;
}

export function ScheduleSlotEditor({ value, onChange }: { value: DraftScheduleSlot[]; onChange: (value: DraftScheduleSlot[]) => void }) {
  const update = (index: number, patch: Partial<DraftScheduleSlot>) => onChange(value.map((slot, i) => i === index ? { ...slot, ...patch } : slot));
  return <fieldset className="slotEditor"><legend>Розклад групи</legend>{value.map((slot, index) => <div className="slotRow" key={index}>
    <WeekdayPicker value={slot.weekday} onChange={(weekday) => update(index, { weekday })} />
    <TimeSelect label="Початок" value={slot.start_time} onChange={(start_time) => update(index, { start_time })} />
    <DurationSelect value={slot.duration_minutes} onChange={(duration_minutes) => update(index, { duration_minutes })} />
    <button type="button" className="link danger" onClick={() => onChange(value.filter((_, i) => i !== index))}>Видалити</button>
  </div>)}<button type="button" className="search" onClick={() => onChange([...value, { weekday: (value.at(-1)?.weekday ?? -1) + 1 > 6 ? 0 : (value.at(-1)?.weekday ?? -1) + 1, start_time: "17:00", duration_minutes: 60 }])}>+ Додати день</button></fieldset>;
}

export function AvailabilityWindowEditor({ value, onChange }: { value: AvailabilityWindowDraft[]; onChange: (value: AvailabilityWindowDraft[]) => void }) {
  const update = (index: number, patch: Partial<AvailabilityWindowDraft>) => onChange(value.map((window, i) => i === index ? { ...window, ...patch } : window));
  const toggleDay = (index: number, weekday: number) => {
    const window = value[index];
    if (!window) return;
    const weekdays = window.weekdays.includes(weekday)
      ? window.weekdays.filter((day) => day !== weekday)
      : [...window.weekdays, weekday].sort((a, b) => a - b);
    update(index, { weekdays });
  };

  return <div className="availabilityEditor">
    {value.map((window, index) => <div className="availabilityRow availabilityWindowRow" key={window.id}>
      <div className="availabilityWeekdays">
        <span>Дні</span>
        <div className="availabilityDayChecks">
          {DAY_NAMES.map((day, weekday) => <label className={"availabilityDayCheck" + (window.weekdays.includes(weekday) ? " checked" : "")} key={day}>
            <input type="checkbox" checked={window.weekdays.includes(weekday)} onChange={() => toggleDay(index, weekday)} />
            <span>{day}</span>
          </label>)}
        </div>
        {window.weekdays.length === 0 && <small className="availabilityDayError">Оберіть хоча б один день</small>}
      </div>
      <div className="availabilityTimes">
        <TimeSelect label="Від" value={window.start_time} onChange={(start_time) => update(index, { start_time })} />
        <TimeSelect label="До" value={window.end_time} onChange={(end_time) => update(index, { end_time })} />
      </div>
      <label>Пріоритет<select value={window.preference ?? "preferred"} onChange={(e) => update(index, { preference: e.target.value as AvailabilitySlot["preference"] })}><option value="preferred">Бажано</option><option value="possible">Можливо</option><option value="avoid">Небажано</option></select></label>
      <label className="windowNote">Коментар<input value={window.note ?? ""} onChange={(e) => update(index, { note: e.target.value || null })} placeholder="Необов’язково" /></label>
      <button type="button" className="link danger availabilityDeleteWindow" onClick={() => onChange(value.filter((_, i) => i !== index))}>Видалити</button>
    </div>)}
    <button type="button" className="search availabilityAddWindow" onClick={() => onChange([...value, {
      id: crypto.randomUUID(),
      weekdays: [],
      start_time: "17:00",
      end_time: "19:00",
      preference: "preferred",
      note: null,
    }])}>+ Додати бажаний час</button>
  </div>;
}

export function DateTimeEditor({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  const [date, clock = "17:00"] = value.split("T");
  return <div className="dateTimeEditor"><label>Дата<input type="date" aria-label={label + ": дата"} value={date} onChange={(e) => onChange(`${e.target.value}T${clock}`)} /></label><TimeSelect label="Час" value={clock} onChange={(time) => onChange(`${date}T${time}`)} /></div>;
}

