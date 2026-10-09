// Stage 2 modular groups workspace; state and business actions remain in App.
import { availabilityLabel } from "../leads/availability";
import type { EntityId, Lead } from "../leads/model";
import { candidateCompatibility, MatchBadge, MatchExplanation } from "./matching";
import type { GroupItem } from "./types";
import type { LocationDemo } from "../locations/types";
import type { DraftScheduleSlot } from "../../components/ScheduleEditors";

export type CandidateAgeFilter = "all" | "8-10" | "11-13";
export type CandidateMatchFilter = "all" | "match" | "partial" | "conflict" | "unknown";
export type CandidateSort = "match" | "age" | "name";

type GroupsViewProps = {
  groups: GroupItem[];
  waiting: Lead[];
  visibleWaiting: Lead[];
  candidateLevels: string[];
  locations: LocationDemo[];
  selectedCandidates: EntityId[];
  candidateAgeFilter: CandidateAgeFilter;
  candidateLevelFilter: string;
  candidateLocationFilter: string;
  candidateMatchFilter: CandidateMatchFilter;
  candidateSort: CandidateSort;
  groupSchedule: DraftScheduleSlot[];
  groupLocationId: EntityId | "";
  groupQuery: string;
  groupSort: "name" | "size_desc" | "size_asc";
  groupPageTotal: number;
  groupPageLimit: number;
  groupPageOffset: number;
  groupPageLoading: boolean;
  groupPageError: string;
  onGroupQueryChange: (value: string) => void;
  onGroupSortChange: (value: "name" | "size_desc" | "size_asc") => void;
  onPreviousGroupPage: () => void;
  onNextGroupPage: () => void;
  teacherNameForGroup: (groupId: EntityId) => string | undefined;
  onOpenGroup: (groupId: EntityId) => void;
  onOpenCreation: (context: "groups" | "candidates") => void;
  onToggleCandidate: (studentId: EntityId) => void;
  onCandidateAgeFilterChange: (value: CandidateAgeFilter) => void;
  onCandidateLevelFilterChange: (value: string) => void;
  onCandidateLocationFilterChange: (value: string) => void;
  onCandidateMatchFilterChange: (value: CandidateMatchFilter) => void;
  onCandidateSortChange: (value: CandidateSort) => void;
};

export function GroupsView({
  groups,
  waiting,
  visibleWaiting,
  candidateLevels,
  locations,
  selectedCandidates,
  candidateAgeFilter,
  candidateLevelFilter,
  candidateLocationFilter,
  candidateMatchFilter,
  candidateSort,
  groupSchedule,
  groupLocationId,
  groupQuery,
  groupSort,
  groupPageTotal,
  groupPageLimit,
  groupPageOffset,
  groupPageLoading,
  groupPageError,
  onGroupQueryChange,
  onGroupSortChange,
  onPreviousGroupPage,
  onNextGroupPage,
  teacherNameForGroup,
  onOpenGroup,
  onOpenCreation,
  onToggleCandidate,
  onCandidateAgeFilterChange,
  onCandidateLevelFilterChange,
  onCandidateLocationFilterChange,
  onCandidateMatchFilterChange,
  onCandidateSortChange,
}: GroupsViewProps) {
  return <section className="groupsPage" data-testid="groups-workspace">
    <article className="panel groupsPrimary">
      <div className="panelHead groupsPrimaryHead">
        <div>
          <p className="eyebrow">Основне</p>
          <h2>Активні групи</h2>
          <p className="sectionLead">Відкрийте групу, щоб побачити учасників, відвідування, пропуски, оплати та історію.</p>
        </div>
        <div className="groupsHeadActions">
          <label className="registrySearch"><span>Пошук</span><input value={groupQuery} onChange={(e) => onGroupQueryChange(e.target.value)} placeholder="Група, локація або викладач" /></label>
          <label className="candidateSelect">Сортування<select value={groupSort} onChange={(e) => onGroupSortChange(e.target.value as "name" | "size_desc" | "size_asc")}>
            <option value="name">За назвою</option>
            <option value="size_desc">Більші групи</option>
            <option value="size_asc">Менші групи</option>
          </select></label>
          <span className="counter">{groupPageTotal}</span>
          {waiting.length > 0 && <button className="search" onClick={() => document.getElementById("waiting-groups")?.scrollIntoView({ behavior: "smooth" })}>Очікують: {waiting.length}</button>}
          <button className="primary compact" onClick={() => onOpenCreation("groups")}>+ Нова група</button>
        </div>
      </div>

      {groupPageError && <div className="registryError" role="alert">{groupPageError}</div>}
      {groupPageLoading && groups.length === 0 ? <div className="groupsEmptyPrimary"><strong>Завантаження груп…</strong></div>
      : groups.length === 0 ? <div className="groupsEmptyPrimary">
        <strong>{groupQuery.trim() ? "За пошуком груп не знайдено" : "Ще немає створених груп"}</strong>
        <span>{groupQuery.trim() ? "Змініть пошуковий запит або очистьте поле." : "Створіть групу наперед, задайте локацію та регулярний час. Учнів можна додати пізніше."}</span>
        {!groupQuery.trim() && <button className="primary compact" onClick={() => onOpenCreation("groups")}>+ Створити групу</button>}
      </div> : <div className="groupCards groupCardsPrimary">
        {groups.map((group) => {
          const teacherName = group.teacherName ?? teacherNameForGroup(group.id);
          return <button className="groupCard groupCardButton groupCardPrimary groupCardWide" key={group.id} onClick={() => onOpenGroup(group.id)}>
            <div className="groupCardTitleBlock">
              <span className="groupCardIcon">{group.name.slice(0, 1)}</span>
              <div><b>{group.name}</b><small>{teacherName ? "Викладач: " + teacherName : "Викладач не призначений"}</small></div>
            </div>
            <div className="groupCardFact"><small>Розклад</small><b>{group.schedule}</b></div>
            <div className="groupCardFact"><small>Локація</small><b>{group.location}</b></div>
            <div className="groupCardFact groupCardStudents"><small>Учні</small><b>{group.memberCount ?? group.members.length}/{group.capacity}</b></div>
            <strong className="groupCardOpen">Відкрити групу →</strong>
          </button>;
        })}
      </div>}
      <div className="registryPager" aria-label="Сторінки груп">
        <span>{groupPageTotal === 0 ? "0" : `${groupPageOffset + 1}–${Math.min(groupPageOffset + groupPageLimit, groupPageTotal)}`} з {groupPageTotal}</span>
        <div><button disabled={groupPageLoading || groupPageOffset === 0} onClick={onPreviousGroupPage}>← Назад</button><button disabled={groupPageLoading || groupPageOffset + groupPageLimit >= groupPageTotal} onClick={onNextGroupPage}>Далі →</button></div>
      </div>
    </article>

    <section className="waitingSecondary" id="waiting-groups">
      <div className="waitingSecondaryHead">
        <div>
          <p className="eyebrow">Формування нових груп</p>
          <h2>Очікують групу <span>{waiting.length}</span></h2>
          <p>Допоміжний список кандидатів. Використовуйте його, коли потрібно сформувати нову групу або дозаповнити існуючу.</p>
        </div>
      </div>

      <article className="panel waitingPanel">
        <div className="candidateControls">
          <label className="candidateSelect">Вік<select value={candidateAgeFilter} onChange={(e) => onCandidateAgeFilterChange(e.target.value as CandidateAgeFilter)}>
            <option value="all">Усі віки</option>
            <option value="8-10">8–10 років</option>
            <option value="11-13">11–13 років</option>
          </select></label>
          <label className="candidateSelect">Рівень<select value={candidateLevelFilter} onChange={(e) => onCandidateLevelFilterChange(e.target.value)}>
            <option value="all">Усі рівні</option>
            {candidateLevels.map((level) => <option value={level} key={level}>{level}</option>)}
          </select></label>
          <label className="candidateSelect">Бажана локація<select value={candidateLocationFilter} onChange={(e) => onCandidateLocationFilterChange(e.target.value)}>
            <option value="all">Усі локації</option>
            <option value="none">Не вказано</option>
            {locations.filter((location) => location.isActive).map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}
          </select></label>
          <label className="candidateSelect">Сортування<select value={candidateSort} onChange={(e) => onCandidateSortChange(e.target.value as CandidateSort)}>
            <option value="match">Найкращий збіг</option>
            <option value="age">За віком</option>
            <option value="name">За ім’ям</option>
          </select></label>
        </div>

        <div className="candidateFilters" aria-label="Фільтр за збігом графіка">
          {([["all", "Усі збіги"], ["match", "Підходить"], ["partial", "Частково"], ["conflict", "Узгодити"], ["unknown", "Невідомо"]] as const).map(([value, label]) =>
            <button className={"chip " + (candidateMatchFilter === value ? "active" : "")} onClick={() => onCandidateMatchFilterChange(value)} key={value}>{label}</button>
          )}
        </div>

        <div className="candidateList candidateListSecondary">
          {visibleWaiting.length === 0 && <div className="emptyState">За цим фільтром кандидатів немає.</div>}
          {visibleWaiting.map((lead) => {
            const match = candidateCompatibility(lead, groupSchedule, groupLocationId || null);
            return <label className={"candidate " + (selectedCandidates.includes(lead.id) ? "selected" : "")} key={lead.id}>
              <input type="checkbox" checked={selectedCandidates.includes(lead.id)} onChange={() => onToggleCandidate(lead.id)} />
              <span className="candidateAvatar">{lead.child[0]}</span>
              <span className="candidateMain">
                <b>{lead.child}</b>
                <small>{lead.age} років · {lead.recommendedLevel ?? "Рівень не вказано"}</small>
                <small>{availabilityLabel(lead.availability ?? [])}{lead.preferredLocationName ? " · " + lead.preferredLocationName : ""}</small>
                <MatchExplanation match={match} />
              </span>
              <MatchBadge match={match} />
            </label>;
          })}
        </div>

        <div className="selectionBar">
          <span>Вибрано: <b>{selectedCandidates.length}</b></span>
          <button className="primary" onClick={() => onOpenCreation("candidates")}>{selectedCandidates.length ? "Створити групу з вибраними" : "Створити порожню групу"}</button>
        </div>
      </article>
    </section>
  </section>;
}
