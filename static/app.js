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
  searchEmptyMessage.textContent = results.length ? "" : `По запросу «${query}» ничего не найдено`;
  searchEmptyMessage.classList.toggle("visible", results.length === 0);
  document.getElementById("search-limit-note").hidden = !data.truncated;
    const attribution = document.getElementById("search-attribution");
    attribution.replaceChildren();
    const openSanctions = data.source === "OpenSanctions" || data.dataset === "ru_egrul";
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
const wireguardToggle = document.getElementById("wireguard-enabled");
const wireguardStatus = document.getElementById("wireguard-status");
const wireguardMessage = document.getElementById("wireguard-message");
const settingsAccessDialog = document.getElementById("settings-access-denied");
const settingsForm = document.getElementById("settings-form");
const apiKeyInput = document.getElementById("api-key");
const apiEnabled = document.getElementById("api-enabled");
const settingsMessage = document.getElementById("settings-message");
let apiSettings = { configured: false, enabled: false };
let settingsBusy = false;
let wireguardState = { configured: false, enabled: false, active: false, handshake: false };
let wireguardBusy = false;

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

async function wireguardRequest(method = "GET", enabled) {
  const response = await fetch("/api/settings/wireguard", {
    method,
    headers: { "Content-Type": "application/json", "X-FNS-Settings": "1" },
    body: enabled === undefined ? undefined : JSON.stringify({ enabled }),
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new Error("Сервер вернул некорректный ответ WireGuard."); }
  if (!response.ok) throw new Error(data.message || "Не удалось изменить состояние WireGuard.");
  return data;
}

function showWireguardSettings(data) {
  wireguardState = data;
  wireguardToggle.checked = Boolean(data.active);
  wireguardToggle.disabled = wireguardBusy || !data.configured;
  if (!data.configured) wireguardStatus.textContent = "Конфигурация WireGuard не установлена.";
  else if (data.active && data.handshake) wireguardStatus.textContent = `Туннель подключён · proxy ${data.proxy}`;
  else if (data.active) wireguardStatus.textContent = "Интерфейс включён, ожидается handshake.";
  else wireguardStatus.textContent = "Туннель выключен.";
}

async function refreshWireguardSettings() {
  wireguardBusy = true;
  wireguardToggle.disabled = true;
  wireguardMessage.textContent = "Проверяем состояние туннеля…";
  wireguardMessage.classList.remove("error");
  try {
    showWireguardSettings(await wireguardRequest());
    wireguardMessage.textContent = "";
  } catch (error) {
    wireguardMessage.textContent = error.message;
    wireguardMessage.classList.add("error");
  } finally {
    wireguardBusy = false;
    wireguardToggle.disabled = !wireguardState.configured;
  }
}

wireguardToggle.addEventListener("change", async () => {
  const enabled = wireguardToggle.checked;
  wireguardBusy = true;
  wireguardToggle.disabled = true;
  wireguardMessage.textContent = enabled ? "Подключаем WireGuard…" : "Отключаем WireGuard…";
  wireguardMessage.classList.remove("error");
  try {
    const data = await wireguardRequest("POST", enabled);
    showWireguardSettings(data);
    wireguardMessage.textContent = enabled && !data.handshake
      ? "Интерфейс включён, ожидается handshake."
      : "Состояние WireGuard обновлено.";
  } catch (error) {
    wireguardToggle.checked = Boolean(wireguardState.active);
    wireguardMessage.textContent = error.message;
    wireguardMessage.classList.add("error");
  } finally {
    wireguardBusy = false;
    wireguardToggle.disabled = !wireguardState.configured;
  }
});

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
  } catch (error) {
    if (error.code === "local_network_only") {
      settingsAccessDialog.showModal();
      return;
    }
    settingsDialog.showModal();
    settingsFeedback(error.message, true);
  }
});
document.getElementById("settings-close").addEventListener("click", () => settingsDialog.close());
settingsDialog.addEventListener("close", () => { apiKeyInput.value = ""; });
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
settingsRequest().then(showSettings).catch(() => {});
window.addEventListener("load", refreshIcons, { once: true });
refreshIcons();