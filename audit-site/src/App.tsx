import { useEffect, useState } from "react";
import { Section } from "./components/Section";
import { SeverityBadge, GradeBadge, type Severity } from "./components/Badges";
import { Donut, BarList } from "./components/Charts";
import {
  repo,
  quickStats,
  timeline,
  architectureComponents,
  architectureRisks,
  securityFindings,
  validationVerdicts,
  fieldCompleteness,
  calculatorCoverage,
  testingStats,
  docBloat,
  riskRegister,
  recommendations,
  scorecard,
  overallVerdict,
} from "./data/audit";

const NAV = [
  { id: "overview", label: "Обзор" },
  { id: "architecture", label: "Архитектура" },
  { id: "security", label: "Безопасность" },
  { id: "data-quality", label: "Данные" },
  { id: "testing", label: "Тестирование" },
  { id: "process", label: "Процесс" },
  { id: "risks", label: "Риски" },
  { id: "recommendations", label: "Рекомендации" },
  { id: "verdict", label: "Вердикт" },
];

function useActiveSection() {
  const [active, setActive] = useState("overview");
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setActive(entry.target.id);
        });
      },
      { rootMargin: "-40% 0px -50% 0px" }
    );
    NAV.forEach((n) => {
      const el = document.getElementById(n.id);
      if (el) observer.observe(el);
    });
    return () => observer.disconnect();
  }, []);
  return active;
}

function TopNav() {
  const active = useActiveSection();
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-50 border-b border-slate-800/70 bg-slate-950/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3 sm:px-8">
        <a href="#overview" className="flex items-center gap-2 text-sm font-bold text-white">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-teal-500/20 text-teal-300 ring-1 ring-teal-500/40">⚕</span>
          ANTIBIO — Технический аудит
        </a>
        <nav className="hidden gap-5 lg:flex">
          {NAV.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              className={`text-sm font-medium transition-colors ${
                active === n.id ? "text-teal-300" : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {n.label}
            </a>
          ))}
        </nav>
        <button
          onClick={() => setOpen((o) => !o)}
          className="rounded-md border border-slate-700 px-3 py-1.5 text-sm text-slate-300 lg:hidden"
        >
          Меню
        </button>
      </div>
      {open && (
        <div className="border-t border-slate-800 bg-slate-950 px-5 py-3 lg:hidden">
          <div className="flex flex-col gap-3">
            {NAV.map((n) => (
              <a key={n.id} href={`#${n.id}`} onClick={() => setOpen(false)} className="text-sm text-slate-300">
                {n.label}
              </a>
            ))}
          </div>
        </div>
      )}
    </header>
  );
}

function Hero() {
  return (
    <div className="relative overflow-hidden border-b border-slate-800/60">
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 20% 0%, rgba(20,184,166,0.25), transparent), radial-gradient(ellipse 50% 40% at 90% 10%, rgba(239,68,68,0.15), transparent)",
        }}
      />
      <div className="relative mx-auto max-w-6xl px-5 py-16 sm:px-8 sm:py-24">
        <div className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1 text-xs font-medium text-slate-300">
          <span className="h-1.5 w-1.5 rounded-full bg-teal-400" />
          Независимый технический аудит · {repo.auditDate}
        </div>
        <h1 className="mt-5 max-w-3xl text-3xl font-extrabold leading-tight text-white sm:text-5xl">
          Полный аудит проекта{" "}
          <a href={repo.url} target="_blank" rel="noreferrer" className="text-teal-300 underline decoration-teal-500/40 underline-offset-4">
            {repo.owner}/{repo.name}
          </a>
        </h1>
        <p className="mt-5 max-w-2xl text-base text-slate-300 sm:text-lg">{repo.description}</p>
        <div className="mt-8 flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-4 py-3">
            <GradeBadge grade={overallVerdict.grade} />
            <div>
              <p className="text-xs uppercase tracking-wide text-slate-400">Итоговая оценка</p>
              <p className="text-sm font-semibold text-white">{overallVerdict.label}</p>
            </div>
          </div>
          <a
            href={repo.url}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-slate-700 bg-slate-800/60 px-4 py-3 text-sm font-medium text-slate-200 hover:bg-slate-800"
          >
            Открыть репозиторий на GitHub →
          </a>
        </div>

        <div className="mt-12 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {quickStats.map((s) => (
            <div key={s.label} className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <p className="text-xl font-extrabold text-white sm:text-2xl">{s.value}</p>
              <p className="mt-1 text-xs font-medium text-slate-400">{s.label}</p>
              <p className="text-[11px] text-slate-500">{s.note}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Overview() {
  return (
    <Section id="overview" eyebrow="01 · Введение" title="Что это за проект и в какой он точке">
      <div className="grid gap-10 lg:grid-cols-5">
        <div className="lg:col-span-3 space-y-4 text-sm leading-relaxed text-slate-300">
          <p>
            <strong className="text-white">antibio-calc</strong> — это не просто HTML-калькулятор, а целая платформа:
            Python-пайплайн скачивает и парсит клинические рекомендации с официального API Минздрава РФ
            (<code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">apicr.minzdrav.gov.ru</code>), LLM извлекает
            схемы антибиотикотерапии, «Medical Normalizer» приводит их к структурированному виду, «Clinical Engine»
            обслуживает рекомендации через FastAPI, а конечный артефакт — статичный офлайн PWA-калькулятор
            <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">antibiotic_calc.html</code> — встраивает базу
            на этапе сборки.
          </p>
          <p>
            Разработка идёт крайне интенсивно (54 коммита за ~85 дней) практически одним человеком в связке
            с AI-агентами (об этом прямо говорят файлы <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">AGENTS.md</code> и
            281-килобайтный <code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">AI_LOG.md</code>). Проект использует
            собственную «фазовую» модель управления (P0…P10) с RFC, реестром рисков и «воротами» готовности.
          </p>
          <p>
            Собственные документы репозитория на момент аудита прямо констатируют:{" "}
            <em className="text-slate-200">
              «P5.6 remains open… P6 is blocked»
            </em>{" "}
            — то есть по признанию самого проекта, он не завершён и следующая фаза заблокирована.
          </p>
        </div>
        <div className="lg:col-span-2">
          <ol className="space-y-4 border-l border-slate-800 pl-5">
            {timeline.map((t) => (
              <li key={t.date + t.event} className="relative">
                <span className="absolute -left-[25px] top-1 h-2.5 w-2.5 rounded-full bg-teal-400 ring-4 ring-slate-950" />
                <p className="text-xs font-semibold text-teal-300">{t.date}</p>
                <p className="text-sm text-slate-300">{t.event}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </Section>
  );
}

function Architecture() {
  return (
    <Section id="architecture" eyebrow="02 · Архитектура" title="Компоненты платформы и структурные риски">
      <div className="grid gap-4 sm:grid-cols-2">
        {architectureComponents.map((c) => (
          <div key={c.name} className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
            <p className="text-sm font-bold text-white">{c.name}</p>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">{c.detail}</p>
          </div>
        ))}
      </div>

      <h3 className="mt-12 text-lg font-bold text-white">Ключевые архитектурные находки (Enterprise Architecture Review)</h3>
      <p className="mt-2 text-sm text-slate-400">
        Эти находки задокументированы в самом репозитории (<code className="rounded bg-slate-800 px-1.5 py-0.5 text-xs">ENTERPRISE_ARCHITECTURE_REVIEW.md</code>)
        и подтверждены нами по коду.
      </p>
      <div className="mt-6 space-y-4">
        {architectureRisks.map((r) => (
          <div key={r.id} className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-xs text-slate-500">{r.id}</span>
              <SeverityBadge severity={r.severity as Severity} />
              <p className="text-sm font-semibold text-white">{r.title}</p>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">{r.detail}</p>
          </div>
        ))}
      </div>
    </Section>
  );
}

function SecuritySection() {
  return (
    <Section id="security" eyebrow="03 · Безопасность" title="Секреты, сервер, инциденты">
      <div className="space-y-4">
        {securityFindings.map((f) => (
          <div key={f.title} className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
            <div className="flex flex-wrap items-center gap-3">
              <SeverityBadge severity={f.severity as Severity} />
              <p className="text-sm font-semibold text-white">{f.title}</p>
              <span className="text-xs text-slate-500">· {f.status}</span>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-slate-400">{f.detail}</p>
          </div>
        ))}
      </div>
      <div className="mt-8 rounded-xl border border-orange-500/30 bg-orange-500/5 p-5">
        <p className="text-sm font-semibold text-orange-300">Вывод по безопасности</p>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">
          Инженерная гигиена секретов в текущем состоянии кода выглядит зрелой (env-переменные, .gitignore, gitleaks-конфиг,
          жёсткий CSP, loopback-only сервер). Но был реальный инцидент утечки ключей нескольких LLM-провайдеров, и
          единственное подтверждение его закрытия — самоатттестация владельца, а не независимая проверка. Для
          продукта, работающего с медицинскими данными, это стоит усилить внешним аудитом.
        </p>
      </div>
    </Section>
  );
}

function DataQuality() {
  return (
    <Section id="data-quality" eyebrow="04 · Качество данных" title="Самая критичная часть аудита">
      <div className="grid gap-10 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <p className="text-sm font-bold text-white">Вердикты валидации 2675 извлечённых схем дозирования</p>
          <p className="mt-1 text-xs text-slate-500">Источник: quality_report.md, knowledge_base.json (294 клинические рекомендации)</p>
          <div className="mt-6">
            <Donut data={validationVerdicts} />
          </div>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <p className="text-sm font-bold text-white">Полнота полей после нормализации</p>
          <p className="mt-1 text-xs text-slate-500">Чем ниже — тем больше ручной доработки требует поле</p>
          <div className="mt-6">
            <BarList data={fieldCompleteness} />
          </div>
        </div>
      </div>

      <div className="mt-8 rounded-xl border border-red-500/30 bg-red-500/5 p-6">
        <p className="text-sm font-bold text-red-300">Фактическое покрытие расчёта дозы в готовом калькуляторе</p>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <p className="text-3xl font-extrabold text-white">{calculatorCoverage.totalNosologies}</p>
            <p className="text-xs text-slate-400">нозологий в базе</p>
          </div>
          <div>
            <p className="text-3xl font-extrabold text-emerald-400">{calculatorCoverage.unblocked}</p>
            <p className="text-xs text-slate-400">реально считает дозу</p>
          </div>
          <div>
            <p className="text-3xl font-extrabold text-red-400">{calculatorCoverage.blocked}</p>
            <p className="text-xs text-slate-400">заблокированы (fail-closed)</p>
          </div>
          <div>
            <p className="text-3xl font-extrabold text-white">{calculatorCoverage.drugs}</p>
            <p className="text-xs text-slate-400">препаратов в справочнике</p>
          </div>
        </div>
        <p className="mt-4 text-sm leading-relaxed text-slate-300">{calculatorCoverage.note}</p>
        <p className="mt-3 text-xs leading-relaxed text-slate-500">
          Это результат намеренного «fail-closed» дизайна (лучше не посчитать, чем посчитать неверно) — само по себе
          хорошая инженерная практика для медицинского софта. Но с точки зрения пользователя это означает, что
          заявленные «120 нозологий, 48 препаратов» на практике почти полностью являются справочной информацией, а не
          работающим калькулятором.
        </p>
      </div>
    </Section>
  );
}

function Testing() {
  return (
    <Section id="testing" eyebrow="05 · Тестирование" title="Что и как проверяется">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {testingStats.map((t) => (
          <div key={t.label} className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
            <p className="text-sm font-semibold text-white">{t.value}</p>
            <p className="mt-1 text-xs text-slate-400">{t.label}</p>
          </div>
        ))}
      </div>
      <p className="mt-6 text-sm leading-relaxed text-slate-400">
        Python-слой (Medical Normalizer, Clinical Engine, pipeline) протестирован образцово для мед-проекта такого
        масштаба — близкое к 100% покрытие ключевых модулей, сотни тестов на парсеры доз/маршрутов/частоты. При этом
        JS-логика самого калькулятора (арифметика мг/кг, выбор форм выпуска, разведение для инъекций) встроена инлайном
        в HTML-шаблон и не покрыта модульными тестами на JS-стороне — риск скрытых арифметических ошибок именно в
        коде, который непосредственно считает дозу для врача (в истории коммитов, кстати, зафиксирован и исправлен
        минимум один такой баг — «cefuroxime Infinity»).
      </p>
    </Section>
  );
}

function ProcessSection() {
  return (
    <Section id="process" eyebrow="06 · Процесс и документация" title="Управление проектом: сила и перегрузка">
      <div className="grid gap-8 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6">
          <p className="text-sm font-bold text-white">Объём документации против объёма кода</p>
          <div className="mt-4 flex items-end gap-6">
            <div>
              <p className="text-3xl font-extrabold text-white">{docBloat.mdFiles}</p>
              <p className="text-xs text-slate-400">markdown-файлов</p>
            </div>
            <div>
              <p className="text-3xl font-extrabold text-white">{docBloat.mdLines.toLocaleString("ru-RU")}</p>
              <p className="text-xs text-slate-400">строк документации</p>
            </div>
            <div>
              <p className="text-3xl font-extrabold text-teal-300">{docBloat.ratio}×</p>
              <p className="text-xs text-slate-400">строк документации на 1 строку Python</p>
            </div>
          </div>
          <p className="mt-4 text-sm text-slate-400">Крупнейшие файлы:</p>
          <ul className="mt-2 space-y-1 text-sm text-slate-300">
            {docBloat.biggestFiles.map((f) => (
              <li key={f.name} className="flex justify-between border-b border-slate-800/60 py-1">
                <span className="font-mono text-xs text-slate-400">{f.name}</span>
                <span className="text-xs text-slate-500">{f.size}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-6 text-sm leading-relaxed text-slate-300">
          <p className="text-sm font-bold text-white">Что хорошо</p>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-400">
            <li>Явная маркировка неопределённости («UNKNOWN») вместо угадывания;</li>
            <li>Дисциплина «fail-closed»: агент никогда не подтверждает медицинские данные сам за врача;</li>
            <li>Ссылки на конкретные файлы/строки кода в каждом выводе — проверяемость;</li>
            <li>Реестр архитектурных решений (DECISIONS.md, ADR-подобный подход).</li>
          </ul>
          <p className="mt-5 text-sm font-bold text-white">Что вызывает беспокойство</p>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-400">
            <li>360 markdown-файлов на репозиторий с 1 (по сути) активным разработчиком;</li>
            <li>Многократные самоаудиты приходят к вердикту «NOT COMPLETE» — процесс определяет сам себя как незавершённый снова и снова;</li>
            <li>Обширная «бюрократия фаз» (P0–P10, Sign-off Authority, Owner attestation) для проекта такого размера — риск, что документирование подменяет доставку функциональности;</li>
            <li>Нет .github/workflows — правила из документов не проверяются автоматически.</li>
          </ul>
        </div>
      </div>
    </Section>
  );
}

function Risks() {
  const order: Severity[] = ["critical", "high", "medium", "low"];
  return (
    <Section id="risks" eyebrow="07 · Реестр рисков" title="Сводная таблица находок аудита">
      <div className="overflow-x-auto rounded-xl border border-slate-800">
        <table className="w-full min-w-[720px] border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/60 text-xs uppercase tracking-wide text-slate-400">
              <th className="px-4 py-3 font-semibold">ID</th>
              <th className="px-4 py-3 font-semibold">Область</th>
              <th className="px-4 py-3 font-semibold">Серьёзность</th>
              <th className="px-4 py-3 font-semibold">Находка</th>
              <th className="px-4 py-3 font-semibold">Влияние</th>
            </tr>
          </thead>
          <tbody>
            {[...riskRegister]
              .sort((a, b) => order.indexOf(a.severity as Severity) - order.indexOf(b.severity as Severity))
              .map((r, i) => (
                <tr key={r.id} className={i % 2 === 0 ? "bg-slate-900/20" : "bg-slate-900/40"}>
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-slate-400">{r.id}</td>
                  <td className="whitespace-nowrap px-4 py-3 text-slate-300">{r.area}</td>
                  <td className="px-4 py-3">
                    <SeverityBadge severity={r.severity as Severity} />
                  </td>
                  <td className="px-4 py-3 font-medium text-white">{r.title}</td>
                  <td className="px-4 py-3 text-slate-400">{r.impact}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

function Recommendations() {
  return (
    <Section id="recommendations" eyebrow="08 · Рекомендации" title="Что делать дальше">
      <div className="grid gap-4 sm:grid-cols-2">
        {recommendations.map((r, i) => (
          <div key={r.title} className="rounded-xl border border-slate-800 bg-slate-900/40 p-5">
            <div className="flex items-start gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal-500/15 text-xs font-bold text-teal-300 ring-1 ring-teal-500/30">
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-semibold text-white">{r.title}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{r.detail}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function Verdict() {
  return (
    <Section id="verdict" eyebrow="09 · Итог" title="Итоговый вердикт аудита">
      <div className="overflow-hidden rounded-2xl border border-slate-800">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="bg-slate-900/60 text-xs uppercase tracking-wide text-slate-400">
              <th className="px-5 py-3 font-semibold">Категория</th>
              <th className="px-5 py-3 font-semibold">Оценка</th>
              <th className="px-5 py-3 font-semibold">Комментарий</th>
            </tr>
          </thead>
          <tbody>
            {scorecard.map((s, i) => (
              <tr key={s.category} className={i % 2 === 0 ? "bg-slate-900/20" : "bg-slate-900/40"}>
                <td className="px-5 py-4 font-medium text-white">{s.category}</td>
                <td className="px-5 py-4">
                  <GradeBadge grade={s.grade} />
                </td>
                <td className="px-5 py-4 text-slate-400">{s.comment}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-10 rounded-2xl border border-teal-500/30 bg-teal-500/5 p-6 sm:p-8">
        <div className="flex items-center gap-4">
          <GradeBadge grade={overallVerdict.grade} />
          <div>
            <p className="text-lg font-bold text-white">{overallVerdict.label}</p>
            <p className="text-sm text-slate-400">Общая оценка проекта по итогам аудита</p>
          </div>
        </div>
        <p className="mt-5 text-sm leading-relaxed text-slate-300">
          antibio-calc — амбициозная и во многом дисциплинированная попытка построить прослеживаемую платформу
          клинических знаний поверх официальных рекомендаций Минздрава РФ, с образцовым тестированием ядра
          нормализации и осознанным «fail-closed» подходом к медицинской безопасности. Однако по признанию самой
          проектной документации, платформа архитектурно расколота (движок и провенантность не связаны), 55% сырых
          данных не проходят валидацию, а готовый к использованию расчёт дозы работает лишь для 1 нозологии из 120.
          Это ранняя, активно развивающаяся исследовательская система, а не продукт, готовый к клиническому
          применению.
        </p>
        <p className="mt-4 text-xs leading-relaxed text-slate-500">
          Методология: аудит основан на публичном коде, git-истории (54 коммита) и ~360 markdown-отчётах самого
          репозитория по состоянию на коммит 0cf8e33 (2026-09-29). Аудит не включает динамическое тестирование
          развёрнутого сервиса, пентест инфраструктуры или независимую медицинскую экспертизу клинического
          содержимого.
        </p>
      </div>
    </Section>
  );
}

function Footer() {
  return (
    <footer className="border-t border-slate-800/60 py-10">
      <div className="mx-auto max-w-6xl px-5 text-center text-xs text-slate-500 sm:px-8">
        Отчёт сформирован независимо на основе публичных данных репозитория{" "}
        <a href={repo.url} target="_blank" rel="noreferrer" className="text-teal-400 underline underline-offset-2">
          {repo.owner}/{repo.name}
        </a>
        . Не является медицинским, юридическим или финансовым заключением.
      </div>
    </footer>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <TopNav />
      <Hero />
      <Overview />
      <Architecture />
      <SecuritySection />
      <DataQuality />
      <Testing />
      <ProcessSection />
      <Risks />
      <Recommendations />
      <Verdict />
      <Footer />
    </div>
  );
}
