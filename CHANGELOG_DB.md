# CHANGELOG — clinical database (`db/antibio_db.json`)

Журнал изменений встроенной клинической БД калькулятора. Каждая сборка, меняющая
данные, получает запись: кто/почему (кратко) + машинный diff
(`python db/db_diff.py --git <предыдущий коммит>`). Diff показывает изменения
по записям (блокировка, статус источника, КР), по схемам (поля доз по
возрастным группам) и по справочнику препаратов — это документ для
владельца-врача, а не для git blame.

Формат записи: дата — коммит/ветка — суть — затем вывод `db_diff.py`.

---

## 2026-10-14 — ветка `arena/2013101a-antibio-calc` (PR #1), база 1885894

Суть (аудит `docs/audits/AUDIT_2026-10-14.md`, решения в `DECISIONS.md` 2026-10-14):

- все 48 машинно-извлечённых DOSA-записей закрыты для расчёта
  (`calculation_blocked: true`, статус `EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW`);
  `mkb10` приведён к массивам;
- введён статус `NO_FEDERAL_CR_EXPERT_BASIS` (32 записи без федеральной КР, но с
  документированным основанием — расчётные, янтарный бейдж «БЕЗ КР») и
  `SOURCE_BASIS_MISSING` (3 записи без основания — заблокированы: erysipelas,
  pneumococcal_meningitis, brucellosis);
- `aom_child`: флаг `calculation_blocked` проставлен явно (`false`, раньше ключа не
  было — поведение не изменилось);
- справочник: `concentration_mg_per_ml` для tobramycin (40 мг/мл) и netilmicin
  (25 мг/мл) — объём инъекции теперь рассчитывается;
- **ни одно числовое поле дозировок не менялось** (regimen changes: 0).

Итог: 120 записей, 65 расчётных / 55 заблокированных (было 115 расчётных / 4 заблокированных / 1 без флага).

### DB diff: `1885894:db/antibio_db.json` → `db/antibio_db.json`

- records: 120 → 120 (+0 / −0), changed: 84
- blocked: 4 → 55; newly blocked: 51; newly unblocked: 0
- regimen changes: 0; drug-reference entries changed: 2
- blocked now: anaerobnyi_balanopostit, atopicheskii_dermatit_oslozhnennyi_vtorichnoi_infektsiei, bakterialnyi_keratit_podozrenie_profilaktika_vtorichnoi_bakterialnoi_infektsii_pri_keratite_drugoi_etiologii, bolezn_krona_tonkoi_kishki_krome_terminalnogo_ileita_pri_nalichii_priznakov_sistemnogo_vospaleniia_i_ili_infiltrata, bronkhit_vyzvannyi_m_pneumoniae_ili_c_pneumoniae, brucellosis, defekt_aortolegochnoi_peregorodki, erysipelas, febrilnaia_neitropeniia, febrilnaia_neitropeniia_pri_rake_nosoglotki, gepatoblastoma, gidradenit_gnoinyi, idiopaticheskaia_eritema_koltsevidnaia_tsentrobezhnaia_dare, idiopaticheskii_skolioz, infektsii_amnioticheskoi_polosti_i_plodnykh_obolochek_khorioamnionit, kh_stseplennyi_limfoproliferativnyi_sindrom_khlp_s_otiagoshchennym_infektsionnym_anamnezom, khlamidiinaia_limfogranulema_venericheskaia, khronicheskii_virusnyi_gepatit_v_pri_razvitii_entsefalopatii, kistoznyi_fibroz_situatsiia_vozbuditel_ne_ukazany_vo_fragmente, neiroblastoma_standartnaia_gruppa_riska, neoslozhnennye_gryzhi_perednei_briushnoi_stenki, ostryi_limfoblastnyi_leikoz_limfoblastnaia_limfoma_ostrye_leikozy_neodnoznachnoi_lineinosti, ostryi_mieloidnyi_leikoz_profilaktika_pnevmotsistnoi_pnevmonii_u_patsientov_poluchivshikh_fludarabin, otravlenie_gribami_soderzhashchimi_amanitin, perelom_dna_glaznitsy, perelomy_kostei_taza_povrezhdeniia_tazovogo_koltsa, perelomy_proksimalnogo_otdela_bedrennoi_kosti_endoprotezirovanie_osteosintez_pri_ppobk, pervichnye_immunodefitsity_s_preimushchestvennoi_nedostatochnostiu_sinteza_antitel, piodermiia_gangrenoznaia, pneumococcal_meningitis, pnevmotsistnaia_pnevmoniia, posleoperatsionnaia_ventralnaia_gryzha, povrezhdenie_sviazok_kolennogo_sustava_razryv_pks_khirurgicheskaia_antibiotikoprofilaktika, priobretennye_deformatsii_stopy_pap_infektsii_oblasti_khirurgicheskogo_vmeshatelstva_pri_ortopedicheskikh_operatsiiakh_na_stope, prisoedinenie_infektsii_pri_tkin, profilaktika_pnevmotsistnoi_pnevmonii_pri_naznachenii_rituksimaba, profilaktika_pnevmotsistnoi_pnevmonii_pri_terapii_rituksimabom, profilaktika_pnevmotsistnoi_pnevmonii_u_patsientov_poluchaiushchikh_tsiklofosfamid_i_rituksimab, propionovaia_atsidemiia_atsiduriia, rezervuarit_u_detei_s_iak, rody_odnoplodnye_rodorazreshenie_putem_kesareva_secheniia, serpovidno_kletochnaia_bolezn_profilaktika_infektsii_u_detei_rannego_vozrasta, sistemnyi_skleroz_profilaktika_pnevmotsistnoi_pnevmonii_pri_naznachenii_rituksimaba_i_tsiklofosfamida, starcheskaia_katarakta_profilaktika_ostrogo_bakterialnogo_posleoperatsionnogo_endoftalmita_obpe_pri_operatsii_po_udaleniiu_katarakty, trekhpredserdnoe_serdtse_profilaktika_infektsionnogo_endokardita_posle_khirurgicheskoi_korrektsii, urogenitalnyi_trikhomoniaz, vnutricherepnye_gnoinye_oslozhneniia_meningit_ili_ventrikulit, vrozhdennaia_pnevmoniia, vrozhdennyi_podklapannyi_stenoz_aorty, vykidysh_samoproizvolnyi_abort, zabolevaniia_bartolinovoi_zhelezy_abzh_kbzh
- `calculation_blocked` made explicit (was missing): aom_child
- **actinomycosis** (Актиномикоз):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **anaerobnyi_balanopostit** (Баланопостит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["N48.1, N51.2"] → ["N48.1", "N51.2"]
- **animal_bite** (Укусы животных (профилактика и лечение раневой инфекции)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **anthrax** (Сибирская язва):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **aom_child** (Острый средний отит у детей):
  - calculation_blocked: null → false
- **aspiration_pneumonia** (Аспирационная пневмония):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **asplenia_prophylaxis** (Аспления — антибиотикопрофилактика (пенициллиновая)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **atopicheskii_dermatit_oslozhnennyi_vtorichnoi_infektsiei** (Атопический дерматит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **bacterial_meningitis_empiric** (Бактериальный менингит — эмпирическая терапия):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **bakterialnyi_keratit_podozrenie_profilaktika_vtorichnoi_bakterialnoi_infektsii_pri_keratite_drugoi_etiologii** (Кератит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **bolezn_krona_tonkoi_kishki_krome_terminalnogo_ileita_pri_nalichii_priznakov_sistemnogo_vospaleniia_i_ili_infiltrata** (Болезнь Крона):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["K50, K52.3, K52.9"] → ["K50", "K52.3", "K52.9"]
- **bronkhit_vyzvannyi_m_pneumoniae_ili_c_pneumoniae** (Бронхит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **brucellosis** (Бруцеллёз):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → SOURCE_BASIS_MISSING
- **cellulitis** (Целлюлит / флегмона):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **defekt_aortolegochnoi_peregorodki** (Дефект аортолегочной перегородки):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["I27.8, Q21.4"] → ["I27.8", "Q21.4"]
- **diabetic_foot** (Синдром диабетической стопы (инфекция)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **diphtheria** (Дифтерия):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **diverticulitis** (Острый дивертикулит толстой кишки):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **epididymitis** (Острый эпидидимит / эпидидимоорхит):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **epiglottitis_acute** (Острый эпиглоттит):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **erysipelas** (Рожа у взрослых):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → SOURCE_BASIS_MISSING
- **febrile_neutropenia** (Фебрильная нейтропения (эмпирическая терапия)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **febrilnaia_neitropeniia** (Экстракраниальные герминогенные опухоли):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["C38.1, C48.0, C49.0, C49.5, C49.9, C56, C62, C62.0, C62.1, C62.9, D15, D20, D21, D28, D29, D36"] → ["C38.1", "C48.0", "C49.0", "C49.5", "C49.9", "C56", "C62", "C62.0", "C62.1", "C62.9", "D15", "D20", "D21", "D28", "D29", "D36"]
- **febrilnaia_neitropeniia_pri_rake_nosoglotki** (Рак носоглотки):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **gepatoblastoma** (Гепатобластома):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["C22.2, D13.4"] → ["C22.2", "D13.4"]
- **gidradenit_gnoinyi** (Гидраденит гнойный):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **hap** (Нозокомиальная (внутрибольничная) пневмония):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **idiopaticheskaia_eritema_koltsevidnaia_tsentrobezhnaia_dare** (Эритемы):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **idiopaticheskii_skolioz** (Идиопатический сколиоз):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["M41, M41.0, M41.1, M41.2, M41.3, M41.8, M41.9"] → ["M41", "M41.0", "M41.1", "M41.2", "M41.3", "M41.8", "M41.9"]
- **impetigo** (Импетиго):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **infektsii_amnioticheskoi_polosti_i_plodnykh_obolochek_khorioamnionit** (Инфекции амниотической полости и плодных оболочек (хориоамнионит)):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **intraabdominal_infection** (Интраабдоминальная инфекция (осложнённый аппендицит, перитонит)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **kh_stseplennyi_limfoproliferativnyi_sindrom_khlp_s_otiagoshchennym_infektsionnym_anamnezom** (Первичный иммунодефицит- Х-сцепленный лимфопролиферативный синдром):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["D82.3, D82.8, D84.8, D89.8"] → ["D82.3", "D82.8", "D84.8", "D89.8"]
- **khlamidiinaia_limfogranulema_venericheskaia** (Хламидийная лимфогранулёма (венерическая)):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **khronicheskii_virusnyi_gepatit_v_pri_razvitii_entsefalopatii** (Хронический вирусный гепатит B):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **kistoznyi_fibroz_situatsiia_vozbuditel_ne_ukazany_vo_fragmente** (Кистозный фиброз (муковисцидоз)):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **leptospirosis** (Лептоспироз):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **listeriosis** (Листериоз (менингит, бактериемия)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **lung_abscess_empyema** (Абсцесс лёгкого / эмпиема плевры):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **lyme_disease** (Болезнь Лайма (боррелиоз)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **nec** (Некротизирующий энтероколит (НЭК)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **necrotizing_fasciitis** (Некротизирующий фасциит):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **neiroblastoma_standartnaia_gruppa_riska** (Нейробластома):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["C38.2, C47.0, C47.3, C47.4, C47.5, C47.6, C47.8, C47.9, C48.0, C74.1, C74.9, C76.0, C76.1, C76.2, C76.7, C76.8, D48.3"] → ["C38.2", "C47.0", "C47.3", "C47.4", "C47.5", "C47.6", "C47.8", "C47.9", "C48.0", "C74.1", "C74.9", "C76.0", "C76.1", "C76.2", "C76.7", "C76.8", "D48.3"]
- **neoslozhnennye_gryzhi_perednei_briushnoi_stenki** (Грыжи передней брюшной стенки):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **omphalitis** (Омфалит новорождённых):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **osteomyelitis** (Остеомиелит):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **ostryi_limfoblastnyi_leikoz_limfoblastnaia_limfoma_ostrye_leikozy_neodnoznachnoi_lineinosti** (Острый лимфобластный лейкоз):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["C83.5, C91.0, C95.0"] → ["C83.5", "C91.0", "C95.0"]
- **ostryi_mieloidnyi_leikoz_profilaktika_pnevmotsistnoi_pnevmonii_u_patsientov_poluchivshikh_fludarabin** (Острые миелоидные лейкозы):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["C92.0, C92.3, C92.5, C92.6, C92.7, C92.8, C92.9, C93.0, C94.0, C94.2"] → ["C92.0", "C92.3", "C92.5", "C92.6", "C92.7", "C92.8", "C92.9", "C93.0", "C94.0", "C94.2"]
- **otravlenie_gribami_soderzhashchimi_amanitin** (ТОКСИЧЕСКОЕ ДЕЙСТВИЕ ДРУГИХ ЯДОВИТЫХ ВЕЩЕСТВ, СОДЕРЖАЩИХСЯ В СЪЕДЕННЫХ, ГРИБАХ (НЕ ВКЛЮЧЕНЫ ГРИБЫ ПСИХОДИСЛЕПТИКИ [ГАЛЛЮЦИНОГЕНЫ])):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **perelom_dna_glaznitsy** (Перелом дна глазницы):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **perelomy_kostei_taza_povrezhdeniia_tazovogo_koltsa** (Повреждения тазового кольца):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **perelomy_proksimalnogo_otdela_bedrennoi_kosti_endoprotezirovanie_osteosintez_pri_ppobk** (Переломы проксимального отдела бедренной кости):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["S72.0, S72.1, S72.2, T93.1"] → ["S72.0", "S72.1", "S72.2", "T93.1"]
- **pervichnye_immunodefitsity_s_preimushchestvennoi_nedostatochnostiu_sinteza_antitel** (Первичные иммунодефициты с преимущественной недостаточностью синтеза антител):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **piodermiia_gangrenoznaia** (Пиодермия гангренозная):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **pneumococcal_meningitis** (Пневмококковый менингит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → SOURCE_BASIS_MISSING
- **pnevmotsistnaia_pnevmoniia** (ВИЧ-инфекция у взрослых):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **posleoperatsionnaia_ventralnaia_gryzha** (Послеоперационная вентральная грыжа):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **postop_prophylaxis** (Послеоперационная антибиотикопрофилактика):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **povrezhdenie_sviazok_kolennogo_sustava_razryv_pks_khirurgicheskaia_antibiotikoprofilaktika** (Повреждение связок коленного сустава):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["M23.5, M23.6, S83.4, S83.5, S83.6, S83.7"] → ["M23.5", "M23.6", "S83.4", "S83.5", "S83.6", "S83.7"]
- **priobretennye_deformatsii_stopy_pap_infektsii_oblasti_khirurgicheskogo_vmeshatelstva_pri_ortopedicheskikh_operatsiiakh_na_stope** (Приобретенные деформации стопы):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["M20.1, M20.2, M20.3, M20.4, M20.5, M20.6, M21.3, M21.4, M21.5, M21.6, M21.9"] → ["M20.1", "M20.2", "M20.3", "M20.4", "M20.5", "M20.6", "M21.3", "M21.4", "M21.5", "M21.6", "M21.9"]
- **prisoedinenie_infektsii_pri_tkin** (Первичный иммунодефицит: тяжелая комбинированная иммунная недостаточность):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **profilaktika_pnevmotsistnoi_pnevmonii_pri_naznachenii_rituksimaba** (Семейная средиземноморская лихорадка (Наследственный семейный амилоидоз)):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **profilaktika_pnevmotsistnoi_pnevmonii_pri_terapii_rituksimabom** (Юношеский артрит с системным началом):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **profilaktika_pnevmotsistnoi_pnevmonii_u_patsientov_poluchaiushchikh_tsiklofosfamid_i_rituksimab** (Неспецифический аортоартериит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **propionovaia_atsidemiia_atsiduriia** (Пропионовая ацидемия /ацидурия):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **prostatitis** (Простатит (острый и хронический бактериальный)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **rezervuarit_u_detei_s_iak** (Язвенный колит):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **rody_odnoplodnye_rodorazreshenie_putem_kesareva_secheniia** (Роды одноплодные, родоразрешение путем кесарева сечения):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["O32.0, O32.2, O32.4, O32.8, O34.0, O34.4, O82, O82.0, O82.1, O82.2, O82.8, O82.9"] → ["O32.0", "O32.2", "O32.4", "O32.8", "O34.0", "O34.4", "O82", "O82.0", "O82.1", "O82.2", "O82.8", "O82.9"]
- **sbp** (Спонтанный бактериальный перитонит (СБП)):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **scarlet_fever** (Скарлатина):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **septic_arthritis** (Септический (гнойный) артрит):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **serpovidno_kletochnaia_bolezn_profilaktika_infektsii_u_detei_rannego_vozrasta** (Серповидно-клеточные нарушения):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **sistemnyi_skleroz_profilaktika_pnevmotsistnoi_pnevmonii_pri_naznachenii_rituksimaba_i_tsiklofosfamida** (Системный склероз):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **skin_abscess** (Абсцесс кожи / фурункул / карбункул):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **starcheskaia_katarakta_profilaktika_ostrogo_bakterialnogo_posleoperatsionnogo_endoftalmita_obpe_pri_operatsii_po_udaleniiu_katarakty** (Катаракта старческая):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["H25.0, H25.1, H25.2, H25.8, H25.9"] → ["H25.0", "H25.1", "H25.2", "H25.8", "H25.9"]
- **tetanus** (Столбняк):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **trekhpredserdnoe_serdtse_profilaktika_infektsionnogo_endokardita_posle_khirurgicheskoi_korrektsii** (Трехпредсердное сердце):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **urogenitalnyi_trikhomoniaz** (Урогенитальный трихомониаз):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **uti_prophylaxis** (Профилактика рецидивирующих ИМП):
  - source_verification_status: CR_REFERENCE_CALCULATION → NO_FEDERAL_CR_EXPERT_BASIS
- **vnutricherepnye_gnoinye_oslozhneniia_meningit_ili_ventrikulit** (Черепно-мозговая травма у детей):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **vrozhdennaia_pnevmoniia** (Врожденная пневмония):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **vrozhdennyi_podklapannyi_stenoz_aorty** (Врожденный подклапанный стеноз аорты):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- **vykidysh_samoproizvolnyi_abort** (Выкидыш (самопроизвольный аборт)):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
  - mkb10: ["N85.3, N85.7, O02, O02.0, O02.1, O02.8, O02.9, O03, O03.0, O03.1, O03.3, O03.4, O03.5, O03.6, O03.8, O03.9, O05, O05.0, O05.1, O05.3, O05.4, O05.5, O05.6, O05.8, O05.9, O20, O20.0, O20.8, O20.9"] → ["N85.3", "N85.7", "O02", "O02.0", "O02.1", "O02.8", "O02.9", "O03", "O03.0", "O03.1", "O03.3", "O03.4", "O03.5", "O03.6", "O03.8", "O03.9", "O05", "O05.0", "O05.1", "O05.3", "O05.4", "O05.5", "O05.6", "O05.8", "O05.9", "O20", "O20.0", "O20.8", "O20.9"]
- **zabolevaniia_bartolinovoi_zhelezy_abzh_kbzh** (Болезни бартолиновой железы):
  - calculation_blocked: false → true
  - source_verification_status: CR_REFERENCE_CALCULATION → EXTRACTED_CANDIDATES_PENDING_OWNER_REVIEW
- drug ref **netilmicin**: forms
- drug ref **tobramycin**: forms
