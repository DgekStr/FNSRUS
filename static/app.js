const LABELS = {
  identifier: "Идентификатор запроса", identifier_type: "Тип идентификатора", inn: "ИНН", ogrn: "ОГРН", kpp: "КПП",
  card: "Карточка", type: "Тип контрагента", status: "Статус", name: "Наименование", full: "Полное значение", short: "Сокращённое наименование",
  registration: "Регистрация", date: "Дата регистрации", registering_authority: "Регистрирующий орган", okato: "ОКАТО", oktmo: "ОКТМО",
  address: "Адрес", director: "Руководитель", full_name: "ФИО", position: "Должность", inn_masked: "ИНН физлица (маскированный)", appointed_date: "Дата назначения",
  is_disqualified: "Дисквалификация", is_mass_director: "Массовый руководитель", is_mass_address: "Массовый адрес", founders: "Учредители",
  share_percent: "Доля, %", share_rub: "Доля, руб.", share: "Доля", tax_regime: "Налоговый режим", authorized_capital_rub: "Уставный капитал, руб.",
  msp_status: "Статус МСП", extended: "Дополнительные сведения", okved_main: "Основной ОКВЭД", additional_okveds: "Дополнительные ОКВЭД", code: "Код",
  legal_status: "Юридический статус", status_label_ru: "Статус по реестру", status_changed_at: "Дата изменения статуса", bankruptcy_stage: "Стадия банкротства",
  liquidation_phase: "Стадия ликвидации", exclusion_reason: "Причина исключения", sources_checked: "Проверенные источники", warnings: "Предупреждения", checked_at: "Дата проверки",
  risks: "Риски", overall_risk_level: "Уровень риска", overall_risk_score: "Оценка риска", summary_ru: "Сводка рисков", flags: "Выявленные риски", checks_passed: "Выполненные проверки",
  checks_skipped: "Пропущенные проверки", errors: "Невыполненные проверки", error: "Причина", message_ru: "Пояснение", coverage: "Полнота проверки", total: "Всего проверок",
  answered: "Получено ответов", flagged: "С выявленным риском", clean: "Без выявленного риска", skipped: "Пропущено", failed: "Не выполнено",
  verdict_action: "Вердикт", verdict_reason_ru: "Основание вердикта", recommendations: "Рекомендации", sources: "Источники", sources_queried: "Запрошенные источники", tier: "Режим доступа",
  data_source_meta: "Актуальность карточки", egrul_extract_date: "Дата сведений ЕГРЮЛ", pb_extract_date: "Дата сведений ФНС", efrsb_check_date: "Дата проверки ЕФРСБ",
  pb_fns_check_date: "Дата проверки данных ФНС", fssp_check_date: "Дата проверки ФССП", kad_check_date: "Дата проверки КАД", registries_check_date: "Дата проверки реестров",
  cache_age_hours: "Возраст сохранённых данных, ч", fetched_at: "Дата получения", severity: "Значимость", description: "Описание", details: "Подробности", source: "Источник",
  amount_rub: "Сумма, руб.", count: "Количество", level: "Уровень", title: "Название", url: "Ссылка", reason: "Причина", directors_history: "История руководителей",
  api_fns: "API-ФНС", egr: "Сведения ЕГРЮЛ / ЕГРИП", check: "Аналитика", method: "Метод", api_fns_check_date: "Дата проверки API-ФНС",
  items: "Записи",
};

const VALUES = {
  legal_entity: "Юридическое лицо", individual_entrepreneur: "Индивидуальный предприниматель", ip: "Индивидуальный предприниматель", individual: "Физическое лицо",
  active: "Действующее", liquidating: "В процессе ликвидации", liquidation: "Ликвидация", liquidated: "Ликвидировано", reorganizing: "Реорганизация", bankrupt: "Банкротство",
  excluded: "Исключено из реестра", unknown: "Не определён", low: "Низкий", medium: "Средний", high: "Высокий", critical: "Критический",
  safe_to_proceed: "Можно работать", manual_review_required: "Требуется проверка", high_risk_do_not_proceed: "Высокий риск", impossible_contractor_defunct: "Контрагент прекратил деятельность",
  open: "Открытые источники", inn: "ИНН", ogrn: "ОГРН", egrul: "ЕГРЮЛ / ЕГРИП", efrsb: "ЕФРСБ", fssp: "ФССП", kad: "Картотека арбитражных дел",
  pb_fns: "Открытые данные ФНС", registries: "Локальные реестры ФНС", fns_disqualified: "Реестр дисквалифицированных лиц ФНС",
  api_fns: "API-ФНС", egr: "Сведения ЕГРЮЛ / ЕГРИП", check: "Аналитика",
  api_access_denied: "Нет доступа к API-ФНС", api_quota: "Лимит API-ФНС исчерпан", api_unavailable: "API-ФНС недоступен",
  api_invalid_response: "Некорректный ответ API-ФНС", api_company_mismatch: "Несовпадение карточки API-ФНС", api_timeout: "Таймаут API-ФНС",
  source_unavailable: "Источник недоступен", api_response_large: "Ответ API-ФНС слишком большой",
  mass_address: "Массовый адрес", mass_director: "Массовый руководитель", disqualified_director: "Дисквалификация руководителя", bankruptcy_records: "Банкротство",
  tax_debts: "Налоговая задолженность", enforcement_proceedings: "Исполнительные производства", active_lawsuits: "Арбитражные дела",
  registry_empty: "Реестр не загружен", registry_stale: "Реестр устарел", captcha_required: "Требуется код с картинки", invalid_input: "Некорректный идентификатор",
  osno: "Общая система налогообложения", usn: "Упрощённая система налогообложения", eshn: "Единый сельскохозяйственный налог", patent: "Патентная система",
};

const SECTIONS = [
  { id: "basic", title: "Основные сведения", icon: "building-2" },
  { id: "status", title: "Статус и регистрация", icon: "file-check-2" },
  { id: "leadership", title: "Руководство", icon: "user-round" },
  { id: "address", title: "Адрес", icon: "map-pin" },
  { id: "risks", title: "Риски", icon: "shield-alert" },
  { id: "verdict", title: "Вердикт", icon: "clipboard-check" },
  { id: "okved", title: "ОКВЭД", icon: "list-tree" },
  { id: "api-fns", title: "Аналитика API-ФНС", icon: "file-search" },
  { id: "sources", title: "Источники и актуальность", icon: "database" },
];

const form = document.getElementById("check-form");
const input = document.getElementById("identifier");
const checkButton = document.getElementById("check-button");
const message = document.getElementById("form-message");
const contentView = document.getElementById("content-view");
const searchResultsRows = document.getElementById("search-results-rows");
const searchEmptyMessage = document.getElementById("search-empty-message");
const returnToSearch = document.getElementById("return-to-search");
let report = null;
let activeController = null;
let requestSequence = 0;
let toastTimer = null;
let searchQuery = "";

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const node = element("i");
  node.dataset.lucide = name;
  node.setAttribute("aria-hidden", "true");
  return node;
}

function refreshIcons() {
  window.lucide?.createIcons();
}

const themeToggle = document.getElementById("theme-toggle");
const themeStorageKey = "fnsrus-theme";

function applyTheme(theme, persist = false) {
  const dark = theme === "dark";
  const label = dark ? "Включить светлую тему" : "Включить тёмную тему";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  themeToggle.setAttribute("aria-pressed", String(dark));
  themeToggle.setAttribute("aria-label", label);
  themeToggle.title = label;
  themeToggle.replaceChildren(icon(dark ? "sun" : "moon"));
  document.querySelector('meta[name="theme-color"]').content = dark ? "#151b18" : "#176b50";
  if (persist) {
    try { localStorage.setItem(themeStorageKey, dark ? "dark" : "light"); }
    catch { /* Theme still applies when storage is unavailable. */ }
  }
  refreshIcons();
}

let savedTheme = "light";
try { if (localStorage.getItem(themeStorageKey) === "dark") savedTheme = "dark"; }
catch { /* Default to light when storage is unavailable. */ }
applyTheme(savedTheme);
themeToggle.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark", true);
});

export function validateIdentifier(value) {
  if (!/^(?:[0-9]{10}|[0-9]{12}|[0-9]{13}|[0-9]{15})$/.test(value)) {
    return "Введите ИНН из 10 или 12 цифр либо ОГРН из 13 или 15 цифр.";
  }
  const digits = Array.from(value, Number);
  const checksum = weights => weights.reduce((sum, weight, index) => sum + weight * digits[index], 0) % 11 % 10;
  let valid;
  if (value.length === 10) valid = checksum([2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[9];
  else if (value.length === 12) valid = checksum([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[10] && checksum([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === digits[11];
  else valid = Number(BigInt(value.slice(0, -1)) % (value.length === 13 ? 11n : 13n) % 10n) === digits.at(-1);
  return valid ? "" : "Неверная контрольная цифра ИНН или ОГРН. Проверьте номер.";
}

export function collectLeaves(value, path = []) {
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length) return entries.flatMap(([key, nested]) => collectLeaves(nested, [...path, key]));
  }
  return [{ path, value }];
}

function sectionFor(path) {
  const [root, field] = path;
  if (root === "api_fns") return "api-fns";
  if (root === "card") {
    if (["status", "registration"].includes(field)) return "status";
    if (["director", "directors_history"].includes(field)) return "leadership";
    if (field === "address") return "address";
    if (["okved_main", "additional_okveds"].includes(field)) return "okved";
    if (field === "data_source_meta") return "sources";
    return "basic";
  }
  if (root === "legal_status") return "status";
  if (root === "risks") return "risks";
  if (["verdict_action", "verdict_reason_ru", "recommendations"].includes(root)) return "verdict";
  return "sources";
}

function fieldLabel(path) {
  const filtered = path.filter(part => !["card", "legal_status", "risks", "data_source_meta"].includes(part));
  return filtered.map((part, index) => {
    if (/^[0-9]+$/.test(part)) return `№ ${Number(part) + 1}`;
    if (part === "full" && path.includes("name")) return "Полное наименование";
    if (part === "full" && path.includes("address")) return "Полный адрес";
    if (/[А-Яа-яЁё]/.test(part)) return part;
    return LABELS[part] || `Дополнительное поле ${index + 1}`;
  }).join(" · ");
}

function rawCopyValue(value) {
  return typeof value === "string" ? value : JSON.stringify(value);
}

function displayValue(value) {
  if (value === null || value === "" || (typeof value === "object" && !Object.keys(value).length)) return "—";
  if (typeof value === "boolean") return value ? "Да" : "Нет";
  if (typeof value === "number") return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 8 }).format(value);
  if (typeof value === "string") {
    if (VALUES[value]) return VALUES[value];
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      const timestamp = new Date(value);
      if (!Number.isNaN(timestamp.getTime())) return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(timestamp);
    }
    return value.replace(/«([a-z_]+)»/g, (match, code) => VALUES[code] ? `«${VALUES[code]}»` : match)
      .replace(/antibot-защита/g, "защита от роботов")
      .replace(/antibot-защиты/g, "защиты от роботов")
      .replace(/antibot-защита\./g, "защита от роботов.")
      .replace(/см\. errors/g, "см. ошибки источников");
  }
  return String(value);
}

function setMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
}

function setViewState(state) {
  contentView.classList.remove("state-initial", "state-searching", "state-results", "state-card");
  contentView.classList.add(`state-${state}`);
}

async function copyText(text) {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard unavailable");
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    const previousFocus = document.activeElement;
    const textarea = element("textarea");
    textarea.value = text;
    textarea.readOnly = true;
    textarea.style.cssText = "position:fixed;left:-9999px;top:0;font-size:16px";
    textarea.setAttribute("aria-hidden", "true");
    document.body.append(textarea);
    textarea.select();
    let copied;
    try { copied = document.execCommand("copy"); }
    finally { textarea.remove(); previousFocus?.focus({ preventScroll: true }); }
    if (!copied) throw new Error("copy failed");
  }
}

async function copyWithFeedback(button, value, defaultLabel) {
  const label = button.querySelector("span");
  try {
    await copyText(value);
    clearTimeout(button.copyTimer);
    label.textContent = "Скопировано!";
    button.classList.add("copied");
    button.copyTimer = setTimeout(() => { label.textContent = defaultLabel; button.classList.remove("copied"); }, 2000);
  } catch {
    const toast = document.getElementById("copy-status");
    toast.textContent = "Не удалось скопировать. Разрешите доступ к буферу обмена в браузере.";
    toast.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toast.hidden = true; }, 5000);
  }
}

function renderReport(data, fromSearch = false) {
  report = data;
  document.getElementById("company-name").textContent = data.card?.name?.short || data.card?.name?.full || `Контрагент ${data.inn || data.identifier || ""}`;
  const verdict = document.getElementById("verdict-summary");
  const action = data.verdict_action;
  const tone = action === "safe_to_proceed" ? "safe" : ["high_risk_do_not_proceed", "impossible_contractor_defunct"].includes(action) ? "danger" : "review";
  verdict.className = `verdict-band ${tone}`;
  const verdictText = element("div");
  verdictText.append(element("div", "verdict-title", VALUES[action] || "Требуется проверка"), element("p", "verdict-reason", data.verdict_reason_ru || "Сведения о вердикте отсутствуют."));
  verdict.replaceChildren(icon(tone === "safe" ? "shield-check" : "shield-alert"), verdictText);
  const coverageElement = document.getElementById("coverage-summary");
  coverageElement.replaceChildren();
  const coverage = data.risks?.coverage;
  if (coverage) {
    const answered = element("span");
    answered.append("Ответили источники: ", element("strong", "", `${coverage.answered ?? 0} из ${coverage.total ?? 0}`));
    const failed = element("span");
    failed.append("Не выполнено проверок: ", element("strong", "", String(coverage.failed ?? 0)));
    coverageElement.append(answered, failed);
  }
  const groups = Object.fromEntries(SECTIONS.map(section => [section.id, []]));
  for (const leaf of collectLeaves(data)) groups[sectionFor(leaf.path)].push(leaf);
  const sectionContainer = document.getElementById("sections");
  const navigation = document.getElementById("section-nav");
  sectionContainer.replaceChildren();
  navigation.replaceChildren();
  for (const section of SECTIONS) {
    if (section.id === "api-fns" && !groups[section.id].length) continue;
    const link = element("a", "", section.title);
    link.href = `#${section.id}`;
    navigation.append(link);
    const sectionElement = element("section", "data-section");
    sectionElement.id = section.id;
    const heading = element("h3", "section-heading");
    heading.append(icon(section.icon), document.createTextNode(section.title));
    sectionElement.append(heading);
    const list = element("dl", "field-list");
    for (const leaf of groups[section.id]) {
      const row = element("div", "field-row");
      row.dataset.path = JSON.stringify(leaf.path);
      const label = fieldLabel(leaf.path);
      const visibleValue = displayValue(leaf.value);
      const valueElement = element("dd", `field-value${visibleValue === "—" ? " empty" : ""}`, visibleValue);
      const copyButton = element("button", "copy-field");
      copyButton.type = "button";
      copyButton.title = `Копировать: ${label}`;
      copyButton.setAttribute("aria-label", `Копировать: ${label}`);
      copyButton.append(icon("copy"), element("span", "", "Копировать"));
      copyButton.addEventListener("click", () => copyWithFeedback(copyButton, rawCopyValue(leaf.value), "Копировать"));
      const controls = element("dd");
      controls.style.margin = "0";
      controls.append(copyButton);
      row.append(element("dt", "field-name", label), valueElement, controls);
      list.append(row);
    }
    if (groups[section.id].length) sectionElement.append(list);
    else sectionElement.append(element("p", "section-empty", "—"));
    sectionContainer.append(sectionElement);
  }
  document.getElementById("raw-json").textContent = JSON.stringify(data, null, 2);
  returnToSearch.hidden = !fromSearch;
  setViewState("card");
  refreshIcons();
}

function renderSearchResults(data, query) {
  const results = data.results;
  searchResultsRows.replaceChildren();
  document.getElementById("search-result-count").textContent = results.length ? `Найдено совпадений: ${results.length}` : "";
  searchEmptyMessage.textContent = results.length ? "" : data.partial_sync
    ? `База ещё синхронизируется. По запросу «${query}» пока нет совпадений.`
    : `По запросу «${query}» ничего не найдено`;
  searchEmptyMessage.classList.toggle("visible", results.length === 0);
  document.getElementById("search-limit-note").hidden = !data.truncated;
    const attribution = document.getElementById("search-attribution");
    attribution.replaceChildren();
    const openSanctions = data.source === "OpenSanctions" || data.dataset === "ru_egrul" || data.partial_sync;
    attribution.hidden = !openSanctions;
    if (openSanctions) {
      const sourceLink = element("a", "", "OpenSanctions ru_egrul");
      sourceLink.href = "https://www.opensanctions.org/datasets/ru_egrul/";
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener noreferrer";
      const licenseLink = element("a", "", "CC BY-NC 4.0");
      licenseLink.href = "https://creativecommons.org/licenses/by-nc/4.0/";
      licenseLink.target = "_blank";
      licenseLink.rel = "noopener noreferrer";
      attribution.append("Источник: ", sourceLink, document.createTextNode(". "));
      const dates = [];
      if (data.snapshot_date) dates.push(`снимок ${data.snapshot_date}`);
      if (data.last_source_change) dates.push(`источник изменён ${data.last_source_change}`);
      if (dates.length) attribution.append(document.createTextNode(`${dates.join("; ")}. `));
      attribution.append("Лицензия: ", licenseLink, document.createTextNode(". Только для некоммерческого использования."));
      if (data.partial_sync) {
        attribution.append(
          document.createTextNode(" "),
          element("strong", "partial-sync-warning", "База синхронизируется: результаты неполные, отсутствие компании не является окончательным."),
        );
      }
    }
  for (const result of results) {
    const row = element("tr");
    const name = element("td", "search-result-name", result.name || "—");
    name.dataset.label = "Название";
    const innCell = element("td", "search-result-inn");
    innCell.dataset.label = "ИНН";
    const innButton = element("button", "inn-link", result.inn || "—");
    innButton.type = "button";
    innButton.dataset.inn = result.inn || "";
    innButton.setAttribute("aria-label", `Открыть карточку по ИНН ${result.inn || ""}`);
    innCell.append(innButton);
    const city = element("td", "search-result-city", result.city || "—");
    city.dataset.label = "Город";
    row.append(name, innCell, city);
    searchResultsRows.append(row);
  }
  setViewState("results");
  refreshIcons();
}

function setBusy(busy, action = "check") {
  checkButton.disabled = busy;
  const label = busy ? (action === "search" ? "Ищем…" : "Проверяем…") : "Найти";
  checkButton.replaceChildren(icon(busy ? "loader-circle" : "search"), element("span", "", label));
  if (busy) checkButton.firstChild.classList.add("loading-icon");
  form.setAttribute("aria-busy", String(busy));
  refreshIcons();
}

async function parseApiResponse(response) {
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер вернул некорректный ответ. Попробуйте позже."); }
  if (!response.ok) throw new Error(data.message || data.message_ru || "Не удалось получить сведения. Попробуйте позже.");
  return data;
}

async function searchByName(query) {
  if (checkButton.disabled) return;
  const sequence = ++requestSequence;
  const controller = new AbortController();
  activeController = controller;
  report = null;
  searchQuery = query;
  returnToSearch.hidden = true;
  setViewState("searching");
  document.getElementById("searching-title").textContent = "Ищем по названию…";
  document.getElementById("searching-description").textContent = "Выполняем поиск в реестре ЕГРЮЛ.";
  setBusy(true, "search");
  setMessage("Идёт поиск…");
  const browserTimeout = setTimeout(() => controller.abort(), 65000);
  try {
    const response = await fetch("/api/search", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }), signal: controller.signal,
    });
    const data = await parseApiResponse(response);
    if (!data || !Array.isArray(data.results)) throw new Error("Сервер вернул некорректный ответ поиска.");
    if (sequence !== requestSequence) return;
    renderSearchResults(data, query);
    setMessage("Поиск завершён.");
  } catch (error) {
    if (sequence !== requestSequence) return;
    setViewState("initial");
    setMessage(error.name === "AbortError" ? "Поиск прерван по времени. Попробуйте позже." : error.message, true);
  } finally {
    clearTimeout(browserTimeout);
    if (sequence === requestSequence) { activeController = null; setBusy(false); }
  }
}

async function checkIdentifier(identifier, fromSearch = false) {
  if (checkButton.disabled) return;
  if (!fromSearch) {
    searchQuery = "";
    returnToSearch.hidden = true;
  }
  const sequence = ++requestSequence;
  const controller = new AbortController();
  activeController = controller;
  report = null;
  setViewState("searching");
  document.getElementById("searching-title").textContent = "Проверяем контрагента…";
  document.getElementById("searching-description").textContent = "Получаем сведения из доступных источников.";
  setBusy(true, "check");
  setMessage("Получаем сведения из источников…");
  const browserTimeout = setTimeout(() => controller.abort(), 65000);
  try {
    const response = await fetch("/api/check", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ identifier }), signal: controller.signal,
    });
    const data = await parseApiResponse(response);
    if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("Сервер вернул некорректный ответ.");
    if (sequence !== requestSequence) return;
    renderReport(data, fromSearch);
    setMessage("Проверка завершена.");
  } catch (error) {
    if (sequence !== requestSequence) return;
    input.value = fromSearch ? searchQuery : identifier;
    setViewState(fromSearch ? "results" : "initial");
    setMessage(error.name === "AbortError" ? "Проверка прервана по времени. Попробуйте позже." : error.message, true);
  } finally {
    clearTimeout(browserTimeout);
    if (sequence === requestSequence) { activeController = null; setBusy(false); }
  }
}

form.addEventListener("submit", event => {
  event.preventDefault();
  if (checkButton.disabled) return;
  const value = input.value.trim();
  input.removeAttribute("aria-invalid");
  if (!value) { setMessage("Введите ИНН, ОГРН или название компании.", true); input.focus(); return; }
  if (/^[0-9]+$/.test(value)) {
    const validationError = validateIdentifier(value);
    input.setAttribute("aria-invalid", String(Boolean(validationError)));
    if (validationError) { setMessage(validationError, true); input.focus(); return; }
    void checkIdentifier(value);
    return;
  }
  if (value.length < 2) { setMessage("Введите минимум два символа для поиска.", true); input.focus(); return; }
  void searchByName(value);
});

searchResultsRows.addEventListener("click", event => {
  const button = event.target.closest("button[data-inn]");
  if (!button || checkButton.disabled) return;
  const inn = button.dataset.inn;
  const validationError = validateIdentifier(inn);
  if (validationError) { setMessage(validationError, true); return; }
  input.value = inn;
  void checkIdentifier(inn, true);
});

returnToSearch.addEventListener("click", () => {
  input.value = searchQuery;
  returnToSearch.hidden = true;
  setViewState("results");
  setMessage("Результаты поиска сохранены.");
});

input.addEventListener("input", () => { input.removeAttribute("aria-invalid"); if (message.classList.contains("error")) setMessage(""); });
document.getElementById("clear-button").addEventListener("click", () => {
  requestSequence++;
  activeController?.abort();
  activeController = null;
  report = null;
  searchQuery = "";
  form.reset();
  input.removeAttribute("aria-invalid");
  document.getElementById("sections").replaceChildren();
  document.getElementById("raw-json").textContent = "";
  searchResultsRows.replaceChildren();
  document.getElementById("search-result-count").textContent = "";
  searchEmptyMessage.textContent = "";
  searchEmptyMessage.classList.remove("visible");
  document.getElementById("search-limit-note").hidden = true;
  returnToSearch.hidden = true;
  setViewState("initial");
  setMessage("");
  setBusy(false);
  input.focus();
});
document.getElementById("copy-all").addEventListener("click", event => {
  if (report) copyWithFeedback(event.currentTarget, JSON.stringify(report, null, 2), "Копировать всё");
});

const settingsDialog = document.getElementById("api-settings");
const wireguardAutostart = document.getElementById("wireguard-autostart");
const wireguardSave = document.getElementById("wireguard-save");
const wireguardEnable = document.getElementById("wireguard-enable");
const wireguardDisable = document.getElementById("wireguard-disable");
const wireguardConfigFile = document.getElementById("wireguard-config-file");
const wireguardConfigImport = document.getElementById("wireguard-config-import");
const wireguardConfigEditor = document.getElementById("wireguard-config-editor");
const wireguardConfigSave = document.getElementById("wireguard-config-save");
const wireguardConfigMessage = document.getElementById("wireguard-config-message");
const wireguardStatus = document.getElementById("wireguard-status");
const wireguardMessage = document.getElementById("wireguard-message");
const settingsAccessDialog = document.getElementById("settings-access-denied");
const settingsForm = document.getElementById("settings-form");
const apiKeyInput = document.getElementById("api-key");
const apiEnabled = document.getElementById("api-enabled");
const settingsMessage = document.getElementById("settings-message");
let apiSettings = { configured: false, enabled: false };
let settingsBusy = false;
let wireguardState = { configured: false, control_available: false, enabled: false, active: false, handshake: false };
let wireguardBusy = false;
let wireguardConfigDirty = false;
const opensanctionsStatus = document.getElementById("opensanctions-status");
const opensanctionsProgress = document.getElementById("opensanctions-progress");
const opensanctionsProgressLabel = document.getElementById("opensanctions-progress-label");
const opensanctionsEstimate = document.getElementById("opensanctions-estimate");
const opensanctionsSource = document.getElementById("opensanctions-source");
const opensanctionsPublish = document.getElementById("opensanctions-publish");
const opensanctionsMessage = document.getElementById("opensanctions-message");
const opensanctionsCheck = document.getElementById("opensanctions-check");
const opensanctionsStart = document.getElementById("opensanctions-start");
const opensanctionsStop = document.getElementById("opensanctions-stop");
const opensanctionsStartLabel = document.getElementById("opensanctions-start-label");
const opensanctionsUpdateStatus = document.getElementById("opensanctions-update-status");
const archiveStatus = document.getElementById("archive-status");
const archiveTarget = document.getElementById("archive-target");
const archiveStorage = document.getElementById("archive-storage");
const archivePostgres = document.getElementById("archive-postgres");
const archiveProgress = document.getElementById("archive-progress");
const archiveProgressLabel = document.getElementById("archive-progress-label");
const archivePreflight = document.getElementById("archive-preflight");
const archiveStart = document.getElementById("archive-start");
const archiveStop = document.getElementById("archive-stop");
const archivePreflightStatus = document.getElementById("archive-preflight-status");
const archiveMessage = document.getElementById("archive-message");
let opensanctionsTimer = null;
let opensanctionsPollBusy = false;
let opensanctionsPublishing = false;
let opensanctionsChecking = false;
let opensanctionsStarting = false;
let opensanctionsStopping = false;
let opensanctionsCurrent = null;
let opensanctionsUpdate = null;
let archiveCurrent = null;
let archivePlan = null;
let archivePreflighting = false;
let archiveStarting = false;
let archiveStopping = false;

function showSettings(data) {
  apiSettings = data;
  apiEnabled.checked = data.enabled;
  document.getElementById("source-name").textContent = data.enabled ? "API-ФНС + открытые источники" : "Открытые источники";
  const state = document.getElementById("settings-state");
  state.textContent = data.configured ? (data.enabled ? "API-ФНС подключён" : "Ключ сохранён. API-ФНС отключён") : "API-ФНС не подключён";
  if (data.verified_at) state.textContent += ` · Доступ проверен ${displayValue(data.verified_at)}`;
  apiKeyInput.placeholder = data.configured ? "Новый ключ или ссылка для замены" : "Введите ключ или ссылку регистрации";
  document.getElementById("settings-test").disabled = !data.configured;
  document.getElementById("settings-delete").disabled = !data.configured;
}

async function settingsRequest(method = "GET", body, suffix = "") {
  const response = await fetch(`/api/settings/api-fns${suffix}`, {
    method, headers: { "Content-Type": "application/json", "X-FNS-Settings": "1" },
    body: body === undefined ? undefined : JSON.stringify(body), cache: "no-store",
    signal: AbortSignal.timeout(20000),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер вернул некорректный ответ настроек."); }
  if (!response.ok) {
    const error = new Error(data.message || "Не удалось изменить настройки API.");
    error.code = data.error;
    throw error;
  }
  return data;
}

async function wireguardRequest(method = "GET", body, suffix = "") {
  const response = await fetch(`/api/settings/wireguard${suffix}`, {
    method,
    headers: { "Content-Type": "application/json", "X-FNS-Settings": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(45000),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер вернул некорректный ответ WireGuard."); }
  if (!response.ok) throw new Error(data.message || "Не удалось изменить состояние WireGuard.");
  return data;
}

function showWireguardSettings(data, refreshConfig = false) {
  wireguardState = { ...data, control_available: true };
  wireguardAutostart.checked = Boolean(data.enabled);
  if (refreshConfig || !wireguardConfigDirty) {
    wireguardConfigEditor.value = data.config_text || "";
    wireguardConfigDirty = false;
  }
  if (data.config_error) wireguardStatus.textContent = "Сохранённая конфигурация некорректна; импортируйте исправленный .conf.";
  else if (!data.configured) wireguardStatus.textContent = "Конфигурация WireGuard не установлена.";
  else {
    const connection = data.active
      ? data.handshake ? `Подключён · proxy ${data.proxy}` : "Включён, ожидается handshake"
      : "Выключен";
    const autostart = data.enabled ? "автозапуск включён" : "автозапуск выключен";
    wireguardStatus.textContent = `WireGuard ${connection}; ${autostart}.`;
  }
  updateWireguardControls();
}

function updateWireguardControls() {
  const available = !wireguardBusy && Boolean(wireguardState.configured);
  const configAvailable = !wireguardBusy && Boolean(wireguardState.control_available);
  wireguardAutostart.disabled = !available;
  wireguardSave.disabled = !available || wireguardAutostart.checked === Boolean(wireguardState.enabled) ||
    (Boolean(wireguardState.config_error) && wireguardAutostart.checked);
  wireguardEnable.disabled = !available || Boolean(wireguardState.active) || Boolean(wireguardState.config_error);
  wireguardDisable.disabled = !available || !wireguardState.active;
  wireguardConfigFile.disabled = !configAvailable;
  wireguardConfigImport.disabled = !configAvailable;
  wireguardConfigEditor.disabled = !configAvailable;
  wireguardConfigSave.disabled = !configAvailable || !wireguardConfigDirty;
}

async function refreshWireguardSettings() {
  wireguardBusy = true;
  updateWireguardControls();
  wireguardMessage.textContent = "Проверяем состояние туннеля…";
  wireguardMessage.classList.remove("error");
  try {
    showWireguardSettings(await wireguardRequest(), true);
    wireguardMessage.textContent = "";
  } catch (error) {
    wireguardMessage.textContent = error.message;
    wireguardMessage.classList.add("error");
    wireguardState.control_available = false;
  } finally {
    wireguardBusy = false;
    updateWireguardControls();
  }
}

async function applyWireguardAction(action, enabled) {
  if (wireguardBusy || !wireguardState.configured) return;
  wireguardBusy = true;
  updateWireguardControls();
  wireguardMessage.textContent = action === "save" ? "Сохраняем автозапуск…"
    : action === "enable" ? "Включаем WireGuard…" : "Выключаем WireGuard…";
  wireguardMessage.classList.remove("error");
  try {
    const data = await wireguardRequest(
      "POST", { action, ...(enabled === undefined ? {} : { enabled }) }, "/action",
    );
    showWireguardSettings(data);
    wireguardMessage.textContent = action === "save" ? "Автозапуск WireGuard сохранён."
      : action === "enable" && !data.handshake ? "Интерфейс включён, ожидается handshake."
        : action === "enable" ? "WireGuard включён."
          : "WireGuard выключен.";
  } catch (error) {
    wireguardMessage.textContent = error.message;
    wireguardMessage.classList.add("error");
  } finally {
    wireguardBusy = false;
    updateWireguardControls();
  }
}

wireguardAutostart.addEventListener("change", updateWireguardControls);
wireguardSave.addEventListener("click", () => void applyWireguardAction("save", wireguardAutostart.checked));
wireguardEnable.addEventListener("click", () => void applyWireguardAction("enable"));
wireguardDisable.addEventListener("click", () => void applyWireguardAction("disable"));

wireguardConfigImport.addEventListener("click", () => wireguardConfigFile.click());
wireguardConfigEditor.addEventListener("input", () => {
  wireguardConfigDirty = true;
  updateWireguardControls();
});

wireguardConfigFile.addEventListener("change", async () => {
  const file = wireguardConfigFile.files?.[0];
  wireguardConfigFile.value = "";
  if (!file) return;
  if (file.size > 16384) {
    wireguardConfigMessage.textContent = "Файл превышает допустимый размер 16 КБ.";
    wireguardConfigMessage.classList.add("error");
    return;
  }
  try {
    const text = await file.text();
    if (new TextEncoder().encode(text).byteLength > 16384) throw new Error("Файл превышает допустимый размер 16 КБ.");
    wireguardConfigEditor.value = text;
    wireguardConfigDirty = true;
    wireguardConfigMessage.textContent = "Файл загружен в редактор; проверьте конфигурацию и сохраните её.";
    wireguardConfigMessage.classList.remove("error");
    updateWireguardControls();
  } catch (error) {
    wireguardConfigMessage.textContent = error.message || "Не удалось прочитать файл конфигурации.";
    wireguardConfigMessage.classList.add("error");
  }
});

wireguardConfigSave.addEventListener("click", async () => {
  if (wireguardBusy || !wireguardState.control_available || !wireguardConfigDirty) return;
  if (new TextEncoder().encode(wireguardConfigEditor.value).byteLength > 16384) {
    wireguardConfigMessage.textContent = "Конфигурация превышает допустимый размер 16 КБ.";
    wireguardConfigMessage.classList.add("error");
    return;
  }
  wireguardBusy = true;
  updateWireguardControls();
  wireguardConfigMessage.textContent = "Сохраняем конфигурацию…";
  wireguardConfigMessage.classList.remove("error");
  try {
    const data = await wireguardRequest("POST", { config: wireguardConfigEditor.value }, "/config");
    wireguardConfigDirty = false;
    showWireguardSettings(data, true);
    wireguardConfigMessage.textContent = data.restart_required
      ? "Конфигурация сохранена. Активный туннель не прерван; новые параметры применятся при следующем подключении."
      : "Конфигурация сохранена.";
  } catch (error) {
    wireguardConfigMessage.textContent = error.message;
    wireguardConfigMessage.classList.add("error");
  } finally {
    wireguardBusy = false;
    updateWireguardControls();
  }
});

async function opensanctionsRequest(endpoint = "", method = "GET", body) {
  const response = await fetch(`/api/settings/opensanctions${endpoint}`, {
    method,
    headers: { "Content-Type": "application/json", "X-FNS-Settings": "1" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.timeout(endpoint === "/publish" ? 180000 : endpoint === "/stop" ? 210000 : endpoint ? 60000 : 15000),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер вернул некорректный ответ импорта."); }
  if (!response.ok) {
    const error = new Error(data.message || "Не удалось проверить импорт.");
    error.code = data.error;
    throw error;
  }
  return data;
}

function formatImportCount(value) {
  return new Intl.NumberFormat("ru-RU").format(value);
}

function formatImportDuration(seconds) {
  const minutes = Math.max(1, Math.round(seconds / 60));
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return hours ? `${hours} ч ${String(remainingMinutes).padStart(2, "0")} мин` : `${remainingMinutes} мин`;
}

function formatImportBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let scaled = bytes;
  let unit = 0;
  while (scaled >= 1024 && unit < units.length - 1) { scaled /= 1024; unit++; }
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: unit ? 1 : 0 }).format(scaled)} ${units[unit]}`;
}

function renderOpenSanctionsStatus(data) {
  opensanctionsCurrent = data;
  const labels = {
    not_started: "Импорт ещё не запускался.",
    starting: "Запускается импорт OpenSanctions.",
    checking: "Сверяется версия снимка OpenSanctions.",
    running: "Импорт выполняется.",
    retrying: "Связь прервалась; подготовлена повторная попытка.",
    stopping: "Остановка: сохраняются уже синхронизированные batches.",
    interrupted: "Импорт остановлен; синхронизированные компании сохранены.",
    indexing: "Сканирование завершено; строится поисковый индекс.",
    validating: "Проверяется целостность базы.",
    ready_to_publish: "Импорт завершён; проверенная база готова к публикации.",
    complete: data.published ? "База импортирована и опубликована." : "Импорт завершён.",
    failed: "Импорт завершился с ошибкой.",
  };
  opensanctionsStatus.textContent = labels[data.state] || "Статус импорта неизвестен.";
  opensanctionsStatus.classList.toggle("error", data.state === "failed");

  const total = Number(data.expected_entities);
  const scanned = Number(data.scanned) || 0;
  const imported = Number(data.imported) || 0;
  const synced = Number(data.synced_companies ?? imported) || 0;
  const hasProgress = Number.isFinite(total) && total > 0;
  opensanctionsProgress.hidden = !hasProgress;
  opensanctionsProgressLabel.textContent = hasProgress
    ? `${formatImportCount(scanned)} из ${formatImportCount(total)} строк · ${data.progress_percent ?? 0}% · синхронизировано компаний: ${formatImportCount(synced)}`
    : "";
  if (hasProgress) opensanctionsProgress.value = Math.min(100, Number(data.progress_percent) || 0);

  if (data.state === "running" && data.average_rate_per_second && data.eta_seconds !== null) {
    const completion = new Date(Date.now() + data.eta_seconds * 1000);
    const completionText = new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(completion);
    opensanctionsEstimate.textContent = `Средняя скорость ${formatImportCount(Math.round(data.average_rate_per_second))} строк/с · ориентир сканирования: ${completionText} (около ${formatImportDuration(data.eta_seconds)}).`;
  } else if (data.state === "running") {
    opensanctionsEstimate.textContent = "Средняя оценка появится после двух контрольных обновлений прогресса.";
  } else if (data.state === "checking") {
    opensanctionsEstimate.textContent = "Проверяем metadata index перед загрузкой.";
  } else if (data.state === "retrying") {
    const retryAt = Date.parse(data.retry_at || "");
    const retryRemaining = Number.isFinite(retryAt)
      ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000))
      : Number(data.retry_in_seconds) || 1;
    opensanctionsEstimate.textContent = `Повтор ${data.attempt} из ${data.max_attempts}; следующий старт через ${formatImportDuration(retryRemaining)}. Уже синхронизировано компаний: ${formatImportCount(synced)}.`;
  } else if (data.state === "interrupted") {
    opensanctionsEstimate.textContent = `Сохранено синхронизированных компаний: ${formatImportCount(synced)}. Проверьте версию и запустите resume.`;
  } else if (["indexing", "validating"].includes(data.state)) {
    opensanctionsEstimate.textContent = "Загрузка завершена; выполняются индексация и итоговая проверка.";
  } else {
    opensanctionsEstimate.textContent = "";
  }

  const sourceDates = [
    data.version ? `Снимок ${data.version}` : "",
    data.source_updated_at ? `обновлён ${String(data.source_updated_at).slice(0, 10)}` : "",
    data.last_source_change ? `источник менялся ${String(data.last_source_change).slice(0, 10)}` : "",
  ].filter(Boolean);
  opensanctionsSource.textContent = sourceDates.join(" · ");
  opensanctionsPublish.hidden = !data.can_publish;
  opensanctionsPublish.disabled = opensanctionsPublishing || !data.can_publish;
  const importBusy = data.unit_active || ["starting", "checking", "running", "retrying", "stopping", "indexing", "validating", "ready_to_publish"].includes(data.state);
  const importControlUnavailable = data.import_control_available === false;
  const canStop = Boolean(data.unit_active && data.version);
  opensanctionsStop.hidden = !canStop;
  opensanctionsStop.disabled = opensanctionsStopping || !canStop || data.state === "stopping";
  opensanctionsCheck.hidden = importBusy;
  opensanctionsCheck.disabled = importBusy || importControlUnavailable || opensanctionsChecking;
  if (importBusy) {
    opensanctionsUpdate = null;
    opensanctionsStart.hidden = true;
    opensanctionsStart.disabled = true;
    if (data.state === "retrying") {
      opensanctionsUpdateStatus.textContent = `Связь восстанавливается; повтор ${data.attempt} из ${data.max_attempts}. Остановка сохранит уже синхронизированные данные.`;
    } else if (data.state === "stopping") {
      opensanctionsUpdateStatus.textContent = "Дождитесь сохранения текущей партии; новый запуск временно заблокирован.";
    } else if (["starting", "checking", "running", "indexing", "validating"].includes(data.state)) {
      opensanctionsUpdateStatus.textContent = "Проверка версии и новый запуск недоступны, пока импорт выполняется.";
    } else if (data.state === "ready_to_publish") {
      opensanctionsUpdateStatus.textContent = "Сначала опубликуйте завершённую staging-базу.";
    }
  } else if (data.state === "interrupted") {
    opensanctionsUpdateStatus.textContent = `Импорт прерван. Сохранены ${formatImportCount(synced)} компаний; повторный запуск продолжит синхронизацию без дублей.`;
  } else if (importControlUnavailable) {
    opensanctionsStart.hidden = true;
    opensanctionsStart.disabled = true;
    opensanctionsUpdate = null;
    opensanctionsUpdateStatus.textContent = "Сервис ручного запуска импорта недоступен.";
  } else {
    opensanctionsStart.hidden = !opensanctionsUpdate?.can_start;
    opensanctionsStart.disabled = opensanctionsStarting || !opensanctionsUpdate?.can_start;
    if (opensanctionsUpdate) renderOpenSanctionsUpdate(opensanctionsUpdate);
  }
  if (data.state === "retrying" && data.retry_error) setOpenSanctionsMessage(data.retry_error, true);
  else if (data.state === "interrupted" && data.error) setOpenSanctionsMessage(data.error);
  else if (data.state === "failed" && data.error) setOpenSanctionsMessage(data.error, true);
}

function renderOpenSanctionsUpdate(data) {
  const decisions = {
    initial_import: `База ещё не опубликована. Доступен снимок ${data.latest_version}.`,
    update_available: `Доступно обновление ${data.latest_version}; сейчас опубликована ${data.current_version}.`,
    up_to_date: `Версия ${data.current_version} уже актуальна.`,
    upstream_older: `В источнике ${data.latest_version}, она старее опубликованной ${data.current_version}; откат не запускается.`,
    import_running: "Импорт уже выполняется.",
    publish_required: "Сначала опубликуйте завершённую staging-базу.",
  };
  opensanctionsUpdateStatus.textContent = decisions[data.decision] || "Не удалось определить доступность обновления.";
  opensanctionsCheck.disabled = opensanctionsChecking || opensanctionsCurrent?.can_start_import === false;
  const canStart = Boolean(data.can_start && opensanctionsCurrent?.can_start_import !== false);
  opensanctionsStart.hidden = !canStart;
  opensanctionsStart.disabled = opensanctionsStarting || !canStart;
  opensanctionsStartLabel.textContent = data.decision === "initial_import" ? "Начать импорт" : "Импортировать обновление";
  archivePreflight.disabled = archivePreflighting || !data.latest_version ||
    Boolean(opensanctionsCurrent?.unit_active || archiveCurrent?.archive_active);
}

function setArchiveMessage(text, isError = false) {
  archiveMessage.textContent = text;
  archiveMessage.classList.toggle("error", isError);
}

function renderOpenSanctionsArchiveStatus(data) {
  data = { state: "not_started", ...(data || {}) };
  archiveCurrent = data;
  const labels = {
    not_started: "Полный архив ещё не загружался.",
    checking: "Проверяем snapshot, PostgreSQL и свободное место.",
    starting: "Запускаем загрузку полного архива.",
    downloading: "Архив скачивается.",
    retrying: "Связь прервалась; готовится повторная попытка.",
    stopping: "Останавливаем задачу; завершённые сегменты сохранены.",
    downloaded: "Архив загружен и проверен; готовится импорт PostgreSQL.",
    postgres_importing: "Архив проверен; данные переносятся в PostgreSQL.",
    validating: "Проверяются данные PostgreSQL перед публикацией.",
    complete: "Архив импортирован в PostgreSQL.",
    interrupted: "Задача прервана.",
    failed: "Загрузка или импорт завершились ошибкой.",
  };
  archiveStatus.textContent = labels[data.state] || "Статус архива неизвестен.";
  if (data.state === "interrupted") {
    archiveStatus.textContent = data.download_mode === "parallel"
      ? "Задача прервана; проверенные сегменты можно продолжить."
      : data.download_mode === "single-stream"
        ? "Задача прервана; повторная загрузка начнётся с начала."
        : labels.interrupted;
  }
  archiveStatus.classList.toggle("error", data.state === "failed");
  archiveTarget.textContent = `Каталог: ${data.archive_dir || "не настроен"}`;

  const archiveSize = archivePlan?.archive_size_bytes ?? data.archive_size_bytes;
  const available = Number(archivePlan?.available_bytes ?? data.available_bytes);
  const required = Number(archivePlan?.required_free_bytes ?? data.required_free_bytes);
  const storageParts = [];
  if (archiveSize !== undefined) storageParts.push(`Архив: ${formatImportBytes(archiveSize)}`);
  if (Number.isFinite(available)) storageParts.push(`свободно: ${formatImportBytes(available)}`);
  if (Number.isFinite(required)) storageParts.push(`требуется: ${formatImportBytes(required)}`);
  archiveStorage.textContent = storageParts.join(" · ");

  const postgresErrors = {
    not_configured: "не настроен",
    driver_missing: "драйвер psycopg не установлен",
    connection_failed: "сервер недоступен",
    insufficient_privileges: "не хватает прав на создание таблиц",
  };
  archivePostgres.textContent = data.postgres_ready
    ? "PostgreSQL доступен для импорта."
    : `PostgreSQL ${postgresErrors[data.postgres_error] || "не готов к импорту"}.`;

  const total = Number(data.total_bytes || data.archive_size_bytes);
  const downloaded = Number(data.downloaded_bytes) || 0;
  const postgresScanned = Number(data.postgres_scanned) || 0;
  const expectedEntities = Number(data.expected_entities) || 0;
  if (data.state === "postgres_importing" || data.state === "validating") {
    archiveProgress.hidden = !expectedEntities;
    archiveProgress.value = expectedEntities ? Math.min(100, postgresScanned * 100 / expectedEntities) : 0;
    archiveProgressLabel.textContent = expectedEntities
      ? `Импортировано строк: ${formatImportCount(postgresScanned)} из ${formatImportCount(expectedEntities)} · компаний: ${formatImportCount(data.postgres_synced_companies || 0)}`
      : "Идёт импорт PostgreSQL.";
  } else {
    const hasDownloadProgress = total > 0 && ["starting", "checking", "downloading", "retrying", "stopping", "downloaded", "complete"].includes(data.state);
    archiveProgress.hidden = !hasDownloadProgress;
    archiveProgress.value = total && (data.state === "downloaded" || data.state === "complete")
      ? 100 : total ? Math.min(100, downloaded * 100 / total) : 0;
    archiveProgressLabel.textContent = hasDownloadProgress
      ? `${formatImportBytes(downloaded)} из ${formatImportBytes(total)}`
      : "";
  }

  if (archivePlan) {
    const mode = archivePlan.download_mode === "parallel"
      ? `Range поддерживается: ${archivePlan.parallel_workers || 8} потоков.`
      : "CDN игнорирует Range: будет использован один поток.";
    archivePreflightStatus.textContent = [
      `Снимок ${archivePlan.version}.`,
      mode,
      !archivePlan.space_sufficient ? "Недостаточно свободного места." : "",
      !archivePlan.postgres_ready ? `PostgreSQL: ${postgresErrors[archivePlan.postgres_error] || "не готов"}.` : "",
    ].filter(Boolean).join(" ");
  }

  const active = Boolean(data.archive_active || data.import_active);
  archivePreflight.disabled = archivePreflighting || !opensanctionsUpdate?.latest_version || active;
  archiveStart.hidden = !archivePlan?.can_start;
  archiveStart.disabled = archiveStarting || active || data.can_start === false || !archivePlan?.can_start;
  archiveStop.hidden = !data.archive_active;
  archiveStop.disabled = archiveStopping || !data.archive_active || data.state === "stopping";
  if (data.state === "failed" && data.error) setArchiveMessage(data.error, true);
  else if (data.state === "interrupted" && data.error) setArchiveMessage(data.error);
}

function setOpenSanctionsMessage(text, isError = false) {
  opensanctionsMessage.textContent = text;
  opensanctionsMessage.classList.toggle("error", isError);
}

function scheduleOpenSanctionsRefresh(delay) {
  clearTimeout(opensanctionsTimer);
  if (settingsDialog.open) opensanctionsTimer = setTimeout(() => void refreshOpenSanctionsStatus(), delay);
}

async function refreshOpenSanctionsStatus() {
  if (!settingsDialog.open || opensanctionsPollBusy) return;
  opensanctionsPollBusy = true;
  try {
    const data = await opensanctionsRequest();
    renderOpenSanctionsStatus(data);
    if (data.state !== "failed" && !opensanctionsPublishing) setOpenSanctionsMessage("");
  } catch (error) {
    opensanctionsStatus.textContent = "Статус импорта временно недоступен.";
    setOpenSanctionsMessage(error.message, true);
  }
  try {
    renderOpenSanctionsArchiveStatus(await opensanctionsRequest("/archive"));
  } catch (error) {
    archiveStatus.textContent = "Статус архива временно недоступен.";
    setArchiveMessage(error.message, true);
  } finally {
    opensanctionsPollBusy = false;
    const state = opensanctionsCurrent?.state;
    const importActive = ["starting", "checking", "running", "retrying", "stopping", "indexing", "validating"].includes(state);
    const archiveActive = archiveCurrent?.archive_active ||
      ["starting", "checking", "downloading", "retrying", "stopping", "downloaded", "postgres_importing", "validating"].includes(archiveCurrent?.state);
    if (settingsDialog.open) {
      scheduleOpenSanctionsRefresh(importActive || archiveActive ? 15000 : 30000);
    }
  }
}

async function checkOpenSanctionsUpdate() {
  if (opensanctionsChecking || opensanctionsCurrent?.can_start_import === false) return;
  opensanctionsChecking = true;
  opensanctionsUpdate = null;
  opensanctionsCheck.disabled = true;
  opensanctionsStart.hidden = true;
  archivePlan = null;
  archiveStart.hidden = true;
  archivePreflight.disabled = true;
  opensanctionsUpdateStatus.textContent = "Сверяем версии снимка…";
  archivePreflightStatus.textContent = "";
  setOpenSanctionsMessage("");
  try {
    opensanctionsUpdate = await opensanctionsRequest("/update-check");
    renderOpenSanctionsUpdate(opensanctionsUpdate);
  } catch (error) {
    opensanctionsUpdateStatus.textContent = "Не удалось проверить версию OpenSanctions.";
    setOpenSanctionsMessage(error.message, true);
  } finally {
    opensanctionsChecking = false;
    if (opensanctionsCurrent?.can_start_import) opensanctionsCheck.disabled = false;
  }
}

async function preflightOpenSanctionsArchive() {
  if (archivePreflighting || archiveCurrent?.archive_active || archiveCurrent?.import_active) return;
  if (!opensanctionsUpdate?.latest_version) await checkOpenSanctionsUpdate();
  const version = opensanctionsUpdate?.latest_version;
  if (!version) {
    archivePreflightStatus.textContent = "Сначала дождитесь завершения активного импорта и сверки версии.";
    return;
  }
  archivePreflighting = true;
  archivePreflight.disabled = true;
  archiveStart.hidden = true;
  archivePlan = null;
  archivePreflightStatus.textContent = "Проверяем snapshot, режим загрузки, PostgreSQL и дисковый запас…";
  setArchiveMessage("");
  try {
    archivePlan = await opensanctionsRequest(
      `/archive/preflight?expected_version=${encodeURIComponent(version)}`,
    );
    renderOpenSanctionsArchiveStatus(archiveCurrent || {});
    if (!archivePlan.can_start) {
      archivePreflightStatus.textContent += " Запуск пока недоступен.";
    }
  } catch (error) {
    archivePreflightStatus.textContent = error.message;
    setArchiveMessage(error.message, true);
  } finally {
    archivePreflighting = false;
    archivePreflight.disabled = !opensanctionsUpdate?.latest_version ||
      Boolean(archiveCurrent?.archive_active || archiveCurrent?.import_active);
  }
}

async function startOpenSanctionsArchive() {
  const version = archivePlan?.version;
  if (archiveStarting || !version || !archivePlan?.can_start || archiveCurrent?.can_start === false) return;
  const mode = archivePlan.download_mode === "parallel"
    ? `${archivePlan.parallel_workers || 8} потоков`
    : "один поток (сервер источника игнорирует Range)";
  if (!confirm(
    `Скачать ${formatImportBytes(archivePlan.archive_size_bytes)} в ${archivePlan.archive_path} (${mode}) и затем импортировать данные в PostgreSQL?`,
  )) return;
  archiveStarting = true;
  archiveStart.disabled = true;
  archivePreflight.disabled = true;
  setArchiveMessage("Запускаем фоновую задачу скачивания и импорта…");
  try {
    await opensanctionsRequest("/archive/start", "POST", { expected_version: version });
    archivePlan = null;
    await refreshOpenSanctionsStatus();
    setArchiveMessage("Задача принята systemd; прогресс обновляется автоматически.");
  } catch (error) {
    setArchiveMessage(error.message, true);
    await refreshOpenSanctionsStatus();
  } finally {
    archiveStarting = false;
    archiveStart.disabled = !archivePlan?.can_start || archiveCurrent?.can_start === false;
  }
}

async function stopOpenSanctionsArchive() {
  const version = archiveCurrent?.version;
  if (archiveStopping || !version || !archiveCurrent?.archive_active) return;
  const resumeText = archiveCurrent.download_mode === "parallel"
    ? "Проверенные сегменты сохранятся для продолжения."
    : "При следующем запуске single-stream скачивание начнётся с начала.";
  if (!confirm(`Остановить задачу архива ${version}? ${resumeText}`)) return;
  archiveStopping = true;
  archiveStop.disabled = true;
  setArchiveMessage("Останавливаем задачу…");
  try {
    await opensanctionsRequest("/archive/stop", "POST", { expected_version: version });
    await refreshOpenSanctionsStatus();
    setArchiveMessage(archiveCurrent?.download_mode === "parallel"
      ? "Остановка принята; проверенные сегменты сохранены."
      : "Остановка принята; повторная single-stream загрузка начнётся с начала.");
  } catch (error) {
    setArchiveMessage(error.message, true);
    await refreshOpenSanctionsStatus();
  } finally {
    archiveStopping = false;
    archiveStop.disabled = !archiveCurrent?.archive_active || archiveCurrent?.state === "stopping";
  }
}

async function startOpenSanctionsImport() {
  const expectedVersion = opensanctionsUpdate?.latest_version;
  if (opensanctionsStarting || !expectedVersion || !opensanctionsUpdate?.can_start ||
      opensanctionsCurrent?.can_start_import === false) return;
  const prompt = opensanctionsUpdate.decision === "initial_import"
    ? `Запустить импорт снимка ${expectedVersion}?`
    : `Запустить импорт обновления ${expectedVersion}? Текущая опубликованная база останется доступной до публикации новой.`;
  if (!confirm(prompt)) return;
  opensanctionsStarting = true;
  opensanctionsStart.disabled = true;
  opensanctionsCheck.disabled = true;
  setOpenSanctionsMessage("Запускаем импорт…");
  try {
    const started = await opensanctionsRequest("/import", "POST", { expected_version: expectedVersion });
    opensanctionsUpdate = null;
    renderOpenSanctionsStatus({
      ...(opensanctionsCurrent || {}),
      state: "starting",
      version: started.version,
      scanned: 0,
      imported: 0,
      expected_entities: null,
      progress_percent: null,
      can_publish: false,
      can_start_import: false,
    });
    setOpenSanctionsMessage(`Запуск принят: ${started.version}. Импорт нельзя продублировать.`);
  } catch (error) {
    const message = error.message;
    opensanctionsUpdate = null;
    await refreshOpenSanctionsStatus();
    setOpenSanctionsMessage(message, true);
  } finally {
    opensanctionsStarting = false;
    opensanctionsStart.disabled = !opensanctionsCurrent?.can_start_import || !opensanctionsUpdate?.can_start;
    if (opensanctionsCurrent?.state === "starting") scheduleOpenSanctionsRefresh(1000);
  }
}

async function stopOpenSanctionsImport() {
  const version = opensanctionsCurrent?.version;
  if (opensanctionsStopping || !version || !opensanctionsCurrent?.unit_active) return;
  if (!confirm(`Остановить импорт ${version}? Уже синхронизированные batches сохранятся; запуск можно будет возобновить.`)) return;
  opensanctionsStopping = true;
  opensanctionsStop.disabled = true;
  setOpenSanctionsMessage("Останавливаем процесс и сохраняем текущий batch…");
  try {
    await opensanctionsRequest("/stop", "POST", { expected_version: version });
    opensanctionsUpdate = null;
    await refreshOpenSanctionsStatus();
    setOpenSanctionsMessage("Импорт остановлен; синхронизированные batches сохранены.");
  } catch (error) {
    setOpenSanctionsMessage(error.message, true);
    await refreshOpenSanctionsStatus();
  } finally {
    opensanctionsStopping = false;
    opensanctionsStop.disabled = !opensanctionsCurrent?.unit_active || opensanctionsCurrent?.state === "stopping";
  }
}

function settingsFeedback(text, isError = false) {
  settingsMessage.textContent = text;
  settingsMessage.classList.toggle("error", isError);
}

async function settingsAction(action, successText) {
  if (settingsBusy) return;
  settingsBusy = true;
  settingsFeedback("Проверяем настройки…");
  for (const control of settingsForm.querySelectorAll("input,button")) control.disabled = true;
  try {
    const data = await action();
    apiKeyInput.value = "";
    showSettings(data);
    settingsFeedback(successText);
  } catch (error) {
    settingsFeedback(error.name === "TimeoutError" ? "API-ФНС не ответил вовремя. Попробуйте позже." : error.message, true);
  } finally {
    settingsBusy = false;
    for (const control of settingsForm.querySelectorAll("input,button")) control.disabled = false;
    document.getElementById("settings-test").disabled = !apiSettings.configured;
    document.getElementById("settings-delete").disabled = !apiSettings.configured;
  }
}

document.getElementById("settings-open").addEventListener("click", async () => {
  apiKeyInput.value = "";
  settingsFeedback("");
  document.getElementById("settings-security").hidden = location.protocol === "https:" || ["localhost", "127.0.0.1"].includes(location.hostname);
  try {
    showSettings(await settingsRequest());
    settingsDialog.showModal();
    void refreshWireguardSettings();
    void refreshOpenSanctionsStatus();
  } catch (error) {
    if (error.code === "local_network_only") {
      settingsAccessDialog.showModal();
      return;
    }
    settingsDialog.showModal();
    settingsFeedback(error.message, true);
    void refreshOpenSanctionsStatus();
  }
});
document.getElementById("settings-close").addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("close", () => {
  apiKeyInput.value = "";
  clearTimeout(opensanctionsTimer);
});
document.getElementById("settings-access-denied-close").addEventListener("click", () => settingsAccessDialog.close());
settingsForm.addEventListener("submit", event => {
  event.preventDefault();
  const key = apiKeyInput.value.trim();
  if (key && (key.length < 8 || /[^\x21-\x7e]/.test(key))) { settingsFeedback("Проверьте формат API-ключа.", true); return; }
  if (apiEnabled.checked && !key && !apiSettings.configured) { settingsFeedback("Введите API-ключ.", true); apiKeyInput.focus(); return; }
  settingsAction(() => settingsRequest("POST", { enabled: apiEnabled.checked, ...(key ? { api_key: key } : {}) }), "Настройки сохранены.");
});
document.getElementById("settings-test").addEventListener("click", () => settingsAction(() => settingsRequest("POST", undefined, "/test"), "Доступ к API-ФНС подтверждён."));
document.getElementById("settings-delete").addEventListener("click", () => {
  if (confirm("Удалить сохранённый API-ключ?")) settingsAction(() => settingsRequest("DELETE"), "Ключ удалён. Используются открытые источники.");
});
opensanctionsCheck.addEventListener("click", () => void checkOpenSanctionsUpdate());
opensanctionsStart.addEventListener("click", () => void startOpenSanctionsImport());
opensanctionsStop.addEventListener("click", () => void stopOpenSanctionsImport());
archivePreflight.addEventListener("click", () => void preflightOpenSanctionsArchive());
archiveStart.addEventListener("click", () => void startOpenSanctionsArchive());
archiveStop.addEventListener("click", () => void stopOpenSanctionsArchive());
opensanctionsPublish.addEventListener("click", async () => {
  if (opensanctionsPublishing || !opensanctionsCurrent?.can_publish) return;
  if (!confirm("Опубликовать проверенную базу OpenSanctions и заменить текущую базу поиска?")) return;
  opensanctionsPublishing = true;
  opensanctionsPublish.disabled = true;
  setOpenSanctionsMessage("Публикуем проверенную базу…");
  try {
    await opensanctionsRequest("/publish", "POST", {});
    await refreshOpenSanctionsStatus();
    setOpenSanctionsMessage("База опубликована; поиск доступен.");
  } catch (error) {
    setOpenSanctionsMessage(error.message, true);
    await refreshOpenSanctionsStatus();
  } finally {
    opensanctionsPublishing = false;
    opensanctionsPublish.disabled = !opensanctionsCurrent?.can_publish;
  }
});
settingsRequest().then(showSettings).catch(() => {});
window.addEventListener("load", refreshIcons, { once: true });
refreshIcons();