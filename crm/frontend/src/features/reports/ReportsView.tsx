type FunnelItem = {
  label: string;
  count: number;
};

type ReportsViewProps = {
  conversionPercent: number;
  activeStudentCount: number;
  leadCount: number;
  occupancyPercent: number;
  occupiedSeats: number;
  totalCapacity: number;
  attendanceRate: number;
  attendanceTotal: number;
  paidAmount: string;
  pendingAmount: string;
  overdueAmount: string;
  funnel: FunnelItem[];
  funnelMax: number;
  attendance: {
    present: number;
    late: number;
    absent: number;
    excused: number;
  };
  activeLocations: number;
  activeStaff: number;
  activeGroups: number;
  activeStudents: number;
};

export function ReportsView({
  conversionPercent,
  activeStudentCount,
  leadCount,
  occupancyPercent,
  occupiedSeats,
  totalCapacity,
  attendanceRate,
  attendanceTotal,
  paidAmount,
  pendingAmount,
  overdueAmount,
  funnel,
  funnelMax,
  attendance,
  activeLocations,
  activeStaff,
  activeGroups,
  activeStudents,
}: ReportsViewProps) {
  return <section className="reportsPage">
    <section className="reportStats">
      <article><span>Конверсія в учні</span><strong>{conversionPercent}%</strong><small>{activeStudentCount} з {leadCount} записів</small></article>
      <article><span>Заповненість груп</span><strong>{occupancyPercent}%</strong><small>{occupiedSeats} з {totalCapacity} місць</small></article>
      <article><span>Відвідуваність</span><strong>{attendanceRate}%</strong><small>{attendanceTotal} відміток</small></article>
      <article><span>Сплачено</span><strong>{paidAmount}</strong><small>зафіксовані платежі</small></article>
    </section>

    <section className="reportsGrid">
      <article className="panel">
        <div className="panelHead"><div><p className="eyebrow">Воронка</p><h2>Заявка → учень</h2></div></div>
        <div className="funnelBars">
          {funnel.map((item) => <div className="funnelBar" key={item.label}>
            <span><b>{item.label}</b><i>{item.count}</i></span>
            <div><em style={{ width: Math.max(4, item.count / funnelMax * 100) + "%" }} /></div>
          </div>)}
        </div>
      </article>

      <article className="panel">
        <div className="panelHead"><div><p className="eyebrow">Навчання</p><h2>Відвідування</h2></div><strong className="reportBig">{attendanceRate}%</strong></div>
        <div className="attendanceSummary">
          <span><i className="dot present"></i>Був <b>{attendance.present}</b></span>
          <span><i className="dot late"></i>Запізнився <b>{attendance.late}</b></span>
          <span><i className="dot absent"></i>Відсутній <b>{attendance.absent}</b></span>
          <span><i className="dot excused"></i>Поважна <b>{attendance.excused}</b></span>
        </div>
      </article>

      <article className="panel">
        <div className="panelHead"><div><p className="eyebrow">Фінанси</p><h2>Оплати</h2></div></div>
        <div className="financeRows">
          <span><i>Сплачено</i><b>{paidAmount}</b></span>
          <span><i>Очікується</i><b>{pendingAmount}</b></span>
          <span><i>Прострочено</i><b>{overdueAmount}</b></span>
        </div>
      </article>

      <article className="panel">
        <div className="panelHead"><div><p className="eyebrow">Масштаб</p><h2>Організація</h2></div></div>
        <div className="organizationReport">
          <span><strong>{activeLocations}</strong><small>локацій</small></span>
          <span><strong>{activeStaff}</strong><small>працівників</small></span>
          <span><strong>{activeGroups}</strong><small>груп</small></span>
          <span><strong>{activeStudents}</strong><small>учнів</small></span>
        </div>
      </article>
    </section>
  </section>;
}
