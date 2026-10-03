import { useEffect, useId, useMemo, useRef, useState } from 'react';
import {
  Aperture,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  Copy,
  FileArchive,
  FileJson,
  FolderOpen,
  Github,
  Image as ImageIcon,
  Layers3,
  LayoutDashboard,
  Link2,
  ListFilter,
  LoaderCircle,
  LockKeyhole,
  ScanLine,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  X,
  AlertTriangle,
  Undo2,
} from 'lucide-react';
import {
  DEFAULT_SETTINGS,
  type AuditResult,
  type AuditSettings,
  type Decision,
  type Finding,
  type ImageRecord,
  type InputImage,
  type IssueKind,
  type Split,
} from './types';
import { analyzeFiles } from './audit-client';
import { reanalyze } from './engine';
import { importImages } from './import-client';
import { createDemo } from './demo';
import { downloadReport, downloadManifest, downloadHtml, downloadCleanDataset } from './exports';

type View = 'overview' | 'findings' | 'images' | 'export' | 'guide';
type Filter = 'all' | 'leakage' | 'duplicates' | 'quality';
const NAMES: Record<IssueKind, string> = {
  leakage: 'Split leakage',
  duplicate: 'Exact duplicate',
  similar: 'Visual similarity',
  blur: 'Low sharpness',
  dark: 'Underexposed',
  bright: 'Overexposed',
  small: 'Low resolution',
  broken: 'Unreadable image',
};
const qualityKinds = ['blur', 'dark', 'bright', 'small', 'broken'];
const repo = 'https://github.com/FarzamFattahi/splitlens';
const size = (bytes: number) =>
  bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`;

function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const dialog = ref.current!;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      className={wide ? 'modal wide' : 'modal'}
      onCancel={close}
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <header>
        <h2 id={titleId}>{title}</h2>
        <button className="icon-button" aria-label="Close dialog" onClick={close}>
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}

export default function App() {
  const [view, setView] = useState<View>('overview');
  const [result, setResult] = useState<AuditResult | null>(null);
  const [inputs, setInputs] = useState<InputImage[]>([]);
  const [name, setName] = useState('Product inspection');
  const [demo, setDemo] = useState(true);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<'import' | 'analysis' | 'export'>('analysis');
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const [query, setQuery] = useState('');
  const [splitFilter, setSplitFilter] = useState('all');
  const [settings, setSettings] = useState<AuditSettings>(DEFAULT_SETTINGS);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [selected, setSelected] = useState<Finding | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [page, setPage] = useState(1);
  const abort = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef(result);
  resultRef.current = result;

  async function run(source: InputImage[], datasetName: string, isDemo: boolean) {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setBusy(true);
    setPhase('analysis');
    setProgress({ done: 0, total: source.length });
    setError('');
    setNotice('');
    try {
      const next = await analyzeFiles(
        source,
        settings,
        (done, total) => setProgress({ done, total }),
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setResult(next);
      setInputs(source);
      setName(datasetName);
      setDemo(isDemo);
      setDecisions({});
      setView('overview');
      setSelected(null);
      setPage(1);
      setQuery('');
      setFilter('all');
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : 'Analysis failed. Try a smaller dataset.');
    } finally {
      if (abort.current === controller) setBusy(false);
    }
  }
  async function loadDemo() {
    try {
      await run(await createDemo(), 'Product inspection', true);
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    let active = true;
    createDemo()
      .then((source) => {
        if (active) void run(source, 'Product inspection', true);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
      abort.current?.abort();
    };
  }, []);
  useEffect(() => {
    setPage(1);
  }, [query, splitFilter, filter, view]);
  useEffect(() => {
    if (!notice) return;
    const id = setTimeout(() => setNotice(''), 5000);
    return () => clearTimeout(id);
  }, [notice]);
  async function upload(files: File[]) {
    if (!files.length) return;
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    setError('');
    setBusy(true);
    setPhase('import');
    setProgress({ done: 0, total: 0 });
    try {
      const source = await importImages(files, controller.signal);
      if (controller.signal.aborted) return;
      const first = source[0]?.path.split('/')[0];
      await run(
        source,
        files.length === 1 && files[0].name.endsWith('.zip')
          ? files[0].name.replace(/\.zip$/i, '')
          : first && source[0].path.includes('/')
            ? first
            : 'My image dataset',
        false,
      );
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
      }
    }
  }
  const findings = result?.findings ?? [];
  const flagged = new Set(findings.flatMap((f) => f.imageIds));
  const leakage = findings.filter((f) => f.kind === 'leakage');
  const duplicates = findings.filter((f) => ['duplicate', 'similar'].includes(f.kind));
  const quality = findings.filter((f) => qualityKinds.includes(f.kind));
  const excluded = Object.values(decisions).filter((d) => d === 'exclude').length;
  const images = result?.images ?? [];
  const reviewed = Object.keys(decisions).length;
  const noFlags = images.length - flagged.size;
  const matches = findings.filter(
    (f) =>
      (filter === 'all' ||
        (filter === 'leakage' && f.kind === 'leakage') ||
        (filter === 'duplicates' && ['duplicate', 'similar'].includes(f.kind)) ||
        (filter === 'quality' && qualityKinds.includes(f.kind))) &&
      (!query ||
        f.title.toLowerCase().includes(query.toLowerCase()) ||
        f.imageIds.some((id) =>
          images
            .find((i) => i.id === id)
            ?.path.toLowerCase()
            .includes(query.toLowerCase()),
        )),
  );
  const imageMatches = useMemo(
    () =>
      images.filter(
        (i) =>
          (splitFilter === 'all' || i.split === splitFilter) &&
          i.path.toLowerCase().includes(query.toLowerCase()),
      ),
    [images, splitFilter, query],
  );
  function changeSplit(id: string, split: Split) {
    if (!result) return;
    const next = images.map((i) => (i.id === id ? { ...i, split } : i));
    setResult({ ...result, images: next, findings: reanalyze(next, settings) });
  }
  function decide(id: string, decision?: Decision) {
    setDecisions((prev) => {
      const next = { ...prev };
      if (decision) next[id] = decision;
      else delete next[id];
      return next;
    });
  }
  function applySettings(next: AuditSettings) {
    setSettings(next);
    if (result) setResult({ ...result, settings: next, findings: reanalyze(images, next) });
    setSettingsOpen(false);
    setNotice('Audit thresholds updated. Your review decisions are preserved.');
  }
  function download(kind: 'json' | 'csv' | 'html') {
    if (!result) return;
    try {
      if (kind === 'json') downloadReport(result, decisions, name);
      else if (kind === 'csv') downloadManifest(result, decisions, name);
      else downloadHtml(result, decisions, name);
      setNotice('Report downloaded to your device.');
    } catch (e) {
      setError(String(e));
    }
  }
  async function cleanZip() {
    if (!result) return;
    setBusy(true);
    setPhase('export');
    try {
      await downloadCleanDataset(result, inputs, decisions, name);
      setNotice('Dataset ZIP exported. Original files are unchanged.');
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const navigation: [View, string, typeof LayoutDashboard][] = [
    ['overview', 'Overview', LayoutDashboard],
    ['findings', 'Review findings', ScanLine],
    ['images', 'Image library', ImageIcon],
    ['export', 'Export & handoff', ArrowDownToLine],
  ];
  const previewImages = images.filter((i) => i.thumbnail).slice(0, 5);
  const titles: Record<View, string> = {
    overview: 'Dataset overview',
    findings: 'Review findings',
    images: 'Image library',
    export: 'Export & handoff',
    guide: 'How SplitLens works',
  };

  return (
    <div
      className="app-shell"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        if (!busy) void upload(Array.from(e.dataTransfer.files));
      }}
    >
      <a className="skip-link" href="#main">
        Skip to workspace
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setView('overview');
          }}
        >
          <span className="brand-mark">
            <Aperture size={24} />
          </span>
          SplitLens<span className="version">1.0</span>
        </a>
        <div className="workspace-label">WORKSPACE</div>
        <nav aria-label="Workspace navigation">
          {navigation.map(([id, label, Icon]) => (
            <button
              key={id}
              className={view === id ? 'nav-item active' : 'nav-item'}
              onClick={() => {
                setView(id);
                setQuery('');
              }}
              aria-current={view === id ? 'page' : undefined}
            >
              <Icon size={18} />
              <span>{label}</span>
              {id === 'findings' && findings.length > 0 && (
                <span className="nav-count">{findings.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-card">
            <ShieldCheck size={22} />
            <strong>Your data stays yours.</strong>
            <p>Images are analyzed on this device. No uploads. No account.</p>
            <span>
              <span className="status-dot" /> Local processing
            </span>
          </div>
          <button className="nav-item" onClick={() => setView('guide')}>
            <CircleHelp size={18} />
            How it works
          </button>
          <a className="nav-item" href={repo} target="_blank" rel="noreferrer">
            <Github size={18} />
            View on GitHub
            <ArrowRight size={14} />
          </a>
          <div className="creator">
            Built by{' '}
            <a href="https://github.com/FarzamFattahi" target="_blank" rel="noreferrer">
              Farzam Fattahi
            </a>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{titles[view]}</strong>
          </div>
          <div className="topbar-right">
            <span className="local-label">
              <LockKeyhole size={13} />
              Private by design
            </span>
            <button
              className="icon-button"
              aria-label="Audit settings"
              onClick={() => setSettingsOpen(true)}
              disabled={busy}
            >
              <Settings2 size={19} />
            </button>
            <a
              className="avatar"
              href="https://github.com/FarzamFattahi"
              aria-label="Farzam Fattahi on GitHub"
              target="_blank"
              rel="noreferrer"
            >
              FF
            </a>
          </div>
        </header>
        <main id="main">
          <div className="page-heading">
            <div>
              <div className="eyebrow">IMAGE DATASET PREFLIGHT</div>
              <h1>{titles[view]}</h1>
              <p>
                {view === 'overview'
                  ? 'Know what’s in your dataset. Before your model does.'
                  : view === 'findings'
                    ? 'Inspect the evidence. Make the final call.'
                    : view === 'images'
                      ? 'Every image, its measurements, and your decisions.'
                      : view === 'export'
                        ? 'Turn your review into a reproducible next step.'
                        : 'A small, transparent toolkit for cleaner training data.'}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="button secondary"
                onClick={() => setSettingsOpen(true)}
                disabled={busy}
              >
                <SlidersHorizontal size={16} />
                Configure
              </button>
              <button
                className="button primary"
                onClick={() => fileRef.current?.click()}
                disabled={busy}
              >
                <FolderOpen size={17} />
                Import dataset
              </button>
            </div>
          </div>
          <input
            ref={fileRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/avif,image/bmp,.zip"
            multiple
            hidden
            onChange={(e) => {
              void upload(Array.from(e.target.files ?? []));
              e.target.value = '';
            }}
          />
          <input
            ref={folderRef}
            type="file"
            multiple
            hidden
            {...({
              webkitdirectory: '',
              directory: '',
            } as React.InputHTMLAttributes<HTMLInputElement>)}
            onChange={(e) => {
              void upload(Array.from(e.target.files ?? []));
              e.target.value = '';
            }}
          />
          {error && (
            <div className="notice error" role="alert">
              <AlertTriangle size={18} />
              <span>{error}</span>
              <button aria-label="Dismiss error" onClick={() => setError('')}>
                <X size={16} />
              </button>
            </div>
          )}
          {notice && (
            <div className="notice success" role="status">
              <Check size={18} />
              {notice}
            </div>
          )}
          {busy && (
            <div className="progress-banner" role="status">
              <LoaderCircle size={18} className="spin" />
              <div>
                <strong>
                  {phase === 'analysis'
                    ? `Analyzing ${progress.done} of ${progress.total} images`
                    : phase === 'export'
                      ? 'Preparing dataset ZIP…'
                      : 'Reading dataset safely…'}
                </strong>
                <span>Working locally. You can keep browsing.</span>
              </div>
              <progress
                aria-label="Dataset operation progress"
                value={phase === 'analysis' ? progress.done : undefined}
                max={progress.total || 1}
              />
              {phase !== 'export' && (
                <button
                  className="button small"
                  onClick={() => {
                    abort.current?.abort();
                    setBusy(false);
                    setNotice('Operation canceled. Previous results are preserved.');
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          )}
          {demo && result && (
            <div className="demo-banner">
              <Sparkles size={15} />
              <span>
                <strong>You’re exploring a live demo.</strong> Synthetic images, real analysis.
                Bring your own dataset when you’re ready.
              </span>
              <button onClick={() => folderRef.current?.click()} disabled={busy}>
                Import a folder
                <ArrowRight size={14} />
              </button>
            </div>
          )}
          {!result && !busy && (
            <section className="empty-upload">
              <ScanLine size={42} />
              <h2>A clean start for your next model.</h2>
              <p>
                Drop image files or a ZIP here. Import a folder to preserve train/, val/, and test/
                structure.
              </p>
              <button className="button primary" onClick={() => folderRef.current?.click()}>
                <FolderOpen size={18} />
                Import a folder
              </button>
              <button className="button secondary" onClick={() => void loadDemo()}>
                Explore demo
              </button>
              <small>JPEG, PNG, WebP, AVIF, BMP · Up to 1,500 images / 300 MB</small>
            </section>
          )}
          {result && view === 'overview' && (
            <>
              <section className="dataset-card">
                <div className="dataset-info">
                  <div className="dataset-icon">
                    <Layers3 size={26} />
                  </div>
                  <div>
                    <div className="inline-title">
                      <h2>{name}</h2>
                      <span className="tag neutral">{demo ? 'DEMO DATASET' : 'LOCAL DATASET'}</span>
                    </div>
                    <p>
                      {images.length} images <span>·</span>{' '}
                      {new Set(images.map((i) => i.label)).size} labels <span>·</span>{' '}
                      {size(images.reduce((a, i) => a + i.bytes, 0))}
                    </p>
                    <div className="split-tags">
                      {(['train', 'validation', 'test', 'unassigned'] as Split[]).map((split) => {
                        const n = images.filter((i) => i.split === split).length;
                        return (
                          n > 0 && (
                            <span key={split}>
                              <i className={`split-dot ${split}`} />
                              {split}
                              <b>{n}</b>
                            </span>
                          )
                        );
                      })}
                    </div>
                  </div>
                </div>
                <div className="filmstrip">
                  {previewImages.map((i, n) => (
                    <img
                      key={i.id}
                      src={i.thumbnail}
                      alt={`Demo preview: ${i.label}`}
                      style={{ transform: `rotate(${(n - 2) * 5}deg)` }}
                    />
                  ))}
                </div>
              </section>
              <section className="metrics" aria-label="Audit summary">
                <Metric
                  label="Images analyzed"
                  value={images.length}
                  note={`${(result.elapsed / 1000).toFixed(1)} seconds · on this device`}
                  icon={<ImageIcon size={17} />}
                />
                <Metric
                  label="Leakage candidates"
                  value={leakage.length}
                  note="Across dataset splits"
                  icon={<Link2 size={17} />}
                  danger={leakage.length > 0}
                />
                <Metric
                  label="Duplicate findings"
                  value={duplicates.length}
                  note="Exact + visual similarity"
                  icon={<Copy size={17} />}
                />
                <Metric
                  label="Quality findings"
                  value={quality.length}
                  note="Sharpness, exposure & resolution"
                  icon={<ScanLine size={17} />}
                />
              </section>
              <div className="overview-grid">
                <section className="findings-panel">
                  <div className="section-heading">
                    <div>
                      <h2>What needs a closer look</h2>
                      <p>Start with leakage. Then review duplicates and quality.</p>
                    </div>
                    <button className="text-button" onClick={() => setView('findings')}>
                      View all
                      <ArrowRight size={15} />
                    </button>
                  </div>
                  {findings.length ? (
                    findings
                      .slice(0, 4)
                      .map((f) => (
                        <FindingRow
                          key={f.id}
                          finding={f}
                          images={images}
                          decisions={decisions}
                          onClick={() => setSelected(f)}
                        />
                      ))
                  ) : (
                    <div className="clean-state">
                      <CheckCheck size={28} />
                      <h3>No findings at these thresholds</h3>
                      <p>
                        These checks are a starting point. They do not validate labels or rule out
                        all leakage.
                      </p>
                    </div>
                  )}
                </section>
                <div className="right-column">
                  <section className="coverage-panel">
                    <div className="section-heading">
                      <h2>Review coverage</h2>
                      <ShieldCheck size={17} />
                    </div>
                    <div className="coverage-number">
                      {reviewed}
                      <span>/ {images.length}</span>
                    </div>
                    <p>images with a keep or exclude decision</p>
                    <div className="coverage-track">
                      <span
                        style={{
                          width: `${images.length ? (reviewed / images.length) * 100 : 0}%`,
                        }}
                      />
                    </div>
                    <div className="coverage-detail">
                      <span>
                        <i className="status-dot" />
                        {noFlags} images without flags
                      </span>
                      <span>{excluded} marked for exclusion</span>
                    </div>
                    <button className="button secondary full" onClick={() => setView('findings')}>
                      Continue review
                      <ArrowRight size={16} />
                    </button>
                  </section>
                  <section className="next-panel">
                    <div className="small-label">THE NEXT STEP</div>
                    <h3>A review you can act on.</h3>
                    <p>
                      Export your decisions as a CSV manifest, a visual report, or a curated copy of
                      the dataset.
                    </p>
                    <button className="text-button" onClick={() => setView('export')}>
                      Export & handoff
                      <ArrowRight size={15} />
                    </button>
                  </section>
                </div>
              </div>
              <section className="import-strip">
                <FolderOpen size={20} />
                <div>
                  <strong>Ready for your own dataset?</strong>
                  <span>Folder paths preserve your train / validation / test structure.</span>
                </div>
                <button
                  className="button secondary"
                  onClick={() => folderRef.current?.click()}
                  disabled={busy}
                >
                  Import a folder
                </button>
                <button className="text-button" onClick={() => void loadDemo()} disabled={busy}>
                  Reset demo
                  <Undo2 size={14} />
                </button>
              </section>
            </>
          )}
          {result && view === 'findings' && (
            <section className="library-panel">
              <div className="toolbar">
                <div className="filter-tabs" aria-label="Filter findings">
                  {(
                    [
                      ['all', 'All findings', findings.length],
                      ['leakage', 'Leakage', leakage.length],
                      ['duplicates', 'Duplicates', duplicates.length],
                      ['quality', 'Quality', quality.length],
                    ] as [Filter, string, number][]
                  ).map(([id, label, n]) => (
                    <button
                      aria-pressed={filter === id}
                      className={filter === id ? 'selected' : ''}
                      key={id}
                      onClick={() => setFilter(id)}
                    >
                      {label}
                      <span>{n}</span>
                    </button>
                  ))}
                </div>
                <SearchBox value={query} onChange={setQuery} />
              </div>
              <div className="list-caption">
                <span>{matches.length} findings · candidates require your review</span>
                <span>CLICK TO INSPECT</span>
              </div>
              {matches.slice((page - 1) * 15, page * 15).map((f) => (
                <FindingRow
                  key={f.id}
                  finding={f}
                  images={images}
                  decisions={decisions}
                  onClick={() => setSelected(f)}
                />
              ))}
              {!matches.length && (
                <div className="clean-state">
                  <CheckCheck size={32} />
                  <h3>No matching findings</h3>
                  <p>Try another filter or adjust the audit thresholds.</p>
                </div>
              )}
              <Pagination page={page} total={matches.length} size={15} change={setPage} />
            </section>
          )}
          {result && view === 'images' && (
            <section className="library-panel">
              <div className="toolbar">
                <label className="select-label">
                  <ListFilter size={16} />
                  <select
                    aria-label="Filter by split"
                    value={splitFilter}
                    onChange={(e) => setSplitFilter(e.target.value)}
                  >
                    <option value="all">All splits</option>
                    {['train', 'validation', 'test', 'unassigned'].map((s) => (
                      <option key={s}>{s}</option>
                    ))}
                  </select>
                </label>
                <SearchBox value={query} onChange={setQuery} />
              </div>
              <div className="list-caption">
                {imageMatches.length} images · Split assignment can be corrected below
              </div>
              <div className="image-grid">
                {imageMatches.slice((page - 1) * 24, page * 24).map((i) => (
                  <article className="image-card" key={i.id}>
                    <button
                      className="image-preview"
                      onClick={() =>
                        setSelected({
                          id: `image-${i.id}`,
                          kind: findings.find((f) => f.imageIds.includes(i.id))?.kind ?? 'similar',
                          imageIds: [i.id],
                          title: i.path,
                          detail:
                            findings
                              .filter((f) => f.imageIds.includes(i.id))
                              .map((f) => NAMES[f.kind])
                              .join(' · ') || 'No flags at current thresholds.',
                        })
                      }
                    >
                      {i.thumbnail ? (
                        <img src={i.thumbnail} alt={i.path} loading="lazy" />
                      ) : (
                        <div className="broken-image">
                          <ImageIcon size={26} />
                          Unreadable
                        </div>
                      )}
                      <span className={`decision-badge ${decisions[i.id] ?? ''}`}>
                        {decisions[i.id] ?? (flagged.has(i.id) ? 'Needs review' : 'No flags')}
                      </span>
                    </button>
                    <div className="image-meta">
                      <strong title={i.path}>{i.path.split('/').at(-1)}</strong>
                      <span>
                        {i.width} × {i.height} · {size(i.bytes)}
                      </span>
                      <select
                        aria-label={`Split for ${i.path}`}
                        value={i.split}
                        onChange={(e) => changeSplit(i.id, e.target.value as Split)}
                      >
                        {['train', 'validation', 'test', 'unassigned'].map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </select>
                    </div>
                  </article>
                ))}
              </div>
              {!imageMatches.length && (
                <div className="clean-state">
                  <Search size={28} />
                  <h3>No matching images</h3>
                  <p>Try a different filename or split.</p>
                </div>
              )}
              <Pagination page={page} total={imageMatches.length} size={24} change={setPage} />
            </section>
          )}
          {result && view === 'export' && (
            <>
              <div className="export-summary">
                <CheckCheck size={24} />
                <div>
                  <h2>Your review, made portable.</h2>
                  <p>
                    {images.length} images · {reviewed} reviewed · {excluded} excluded ·{' '}
                    {images.length - excluded} included in the curated copy
                  </p>
                </div>
              </div>
              <div className="export-grid">
                {[
                  {
                    icon: FileArchive,
                    title: 'Curated dataset',
                    description:
                      'A ZIP of original images, minus the files you explicitly excluded. Includes the decision manifest.',
                    button: 'Export dataset ZIP',
                    action: () => void cleanZip(),
                  },
                  {
                    icon: ListFilter,
                    title: 'Decision manifest',
                    description:
                      'One CSV row per image: path, split, measurements, findings, and your keep / exclude decision.',
                    button: 'Download CSV',
                    action: () => download('csv'),
                  },
                  {
                    icon: ScanLine,
                    title: 'Visual audit report',
                    description:
                      'A standalone HTML report with thumbnails and findings. Open it anywhere or share with your team.',
                    button: 'Download report',
                    action: () => download('html'),
                  },
                  {
                    icon: FileJson,
                    title: 'Machine-readable audit',
                    description:
                      'Versioned JSON with analysis settings, image metadata, findings, and decisions. No image bytes.',
                    button: 'Download JSON',
                    action: () => download('json'),
                  },
                ].map((x) => (
                  <section className="export-card" key={x.title}>
                    <x.icon size={27} />
                    <h2>{x.title}</h2>
                    <p>{x.description}</p>
                    <button className="button secondary" disabled={busy} onClick={x.action}>
                      <ArrowDownToLine size={16} />
                      {x.button}
                    </button>
                  </section>
                ))}
              </div>
              <div className="export-note">
                <ShieldCheck size={20} />
                <div>
                  <strong>Originals stay untouched.</strong>
                  <p>
                    Unreviewed images are included. Similarity flags are suggestions. Review before
                    excluding. Exported reports contain filenames; the visual report also contains
                    thumbnails.
                  </p>
                </div>
              </div>
            </>
          )}
          {view === 'guide' && <Guide loadDemo={() => void loadDemo()} />}
          <footer className="workspace-footer">
            <span>
              <span className="status-dot" />
              All image processing happens on your device.
            </span>
            <span>
              Open source · MIT license{' '}
              <a href={repo} target="_blank" rel="noreferrer">
                <Github size={14} />
                <span className="sr-only">GitHub repository</span>
              </a>
            </span>
          </footer>
        </main>
      </div>
      {settingsOpen && (
        <Modal title="Audit settings" close={() => setSettingsOpen(false)}>
          <SettingsForm initial={settings} apply={applySettings} />
        </Modal>
      )}
      {selected && (
        <Modal title={NAMES[selected.kind]} close={() => setSelected(null)} wide>
          <div className="inspector-intro">
            <span className={`tag ${selected.kind === 'leakage' ? 'danger' : 'neutral'}`}>
              {selected.imageIds.length} {selected.imageIds.length === 1 ? 'IMAGE' : 'IMAGES'}
            </span>
            <h3>{selected.title}</h3>
            <p>{selected.detail}</p>
            {selected.distance !== undefined && (
              <p className="mono">dHash Hamming distance: {selected.distance} / 64 bits</p>
            )}
          </div>
          <div className="evidence-grid">
            {selected.imageIds.map((id) => {
              const i = images.find((im) => im.id === id);
              if (!i) return null;
              return (
                <article className="evidence" key={id}>
                  {i.thumbnail ? (
                    <img src={i.thumbnail} alt={i.path} />
                  ) : (
                    <div className="broken-image">
                      <AlertTriangle size={28} />
                      {i.error ?? 'Cannot decode image'}
                    </div>
                  )}
                  <div className="evidence-body">
                    <span className="tag neutral">{i.split}</span>
                    <strong>{i.path}</strong>
                    <div className="measurements">
                      <span>
                        {i.width} × {i.height}
                      </span>
                      <span>Brightness {i.brightness.toFixed(0)} / 255</span>
                      <span>Sharpness {i.sharpness.toFixed(0)}</span>
                    </div>
                    <div className="decision-actions">
                      <button
                        aria-pressed={decisions[id] === 'keep'}
                        className={decisions[id] === 'keep' ? 'button kept' : 'button secondary'}
                        onClick={() => decide(id, 'keep')}
                      >
                        <Check size={16} />
                        Keep
                      </button>
                      <button
                        aria-pressed={decisions[id] === 'exclude'}
                        className={
                          decisions[id] === 'exclude' ? 'button excluded' : 'button secondary'
                        }
                        onClick={() => decide(id, 'exclude')}
                      >
                        <X size={16} />
                        Exclude
                      </button>
                      {decisions[id] && (
                        <button
                          className="icon-button"
                          aria-label={`Reset decision for ${i.path}`}
                          onClick={() => decide(id)}
                        >
                          <Undo2 size={16} />
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
          <div className="modal-footer">
            <span>Your decisions affect exports. Original files are unchanged.</span>
            <button className="button primary" onClick={() => setSelected(null)}>
              Done
              <Check size={16} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  icon,
  danger = false,
}: {
  label: string;
  value: number;
  note: string;
  icon: React.ReactNode;
  danger?: boolean;
}) {
  return (
    <article className="metric">
      <div>
        <span>{label}</span>
        {icon}
      </div>
      <strong className={danger ? 'danger-text' : ''}>{value.toLocaleString()}</strong>
      <p>
        {danger && <span className="warning-dot" />}
        {note}
      </p>
    </article>
  );
}
function SearchBox({ value, onChange }: { value: string; onChange: (s: string) => void }) {
  return (
    <label className="search-box">
      <Search size={16} />
      <span className="sr-only">Search filenames</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Search filenames…"
      />
      {value && (
        <button aria-label="Clear search" onClick={() => onChange('')}>
          <X size={14} />
        </button>
      )}
    </label>
  );
}
function FindingRow({
  finding: f,
  images,
  decisions,
  onClick,
}: {
  finding: Finding;
  images: ImageRecord[];
  decisions: Record<string, Decision>;
  onClick: () => void;
}) {
  const thumbs = f.imageIds.slice(0, 2).map((id) => images.find((i) => i.id === id));
  const reviewed = f.imageIds.every((id) => decisions[id]);
  return (
    <button className="finding-row" onClick={onClick}>
      <div className="finding-thumbs">
        {thumbs.map((i, n) =>
          i?.thumbnail ? (
            <img src={i.thumbnail} key={n} alt="" loading="lazy" />
          ) : (
            <span key={n}>
              <ImageIcon size={22} />
            </span>
          ),
        )}
      </div>
      <div className="finding-text">
        <div>
          <span className={`issue-label ${f.kind === 'leakage' ? 'leakage' : ''}`}>
            {NAMES[f.kind]}
          </span>
          {reviewed && (
            <span className="reviewed">
              <Check size={11} />
              Reviewed
            </span>
          )}
        </div>
        <strong>{f.title}</strong>
        <span>
          {f.imageIds.length} {f.imageIds.length === 1 ? 'image' : 'images'} ·{' '}
          {f.kind === 'leakage'
            ? 'Cross-split match'
            : f.kind === 'duplicate'
              ? 'Identical file content'
              : f.kind === 'similar'
                ? 'Review visual evidence'
                : 'Quality threshold'}
        </span>
      </div>
      <ChevronRight size={18} />
    </button>
  );
}
function Pagination({
  page,
  total,
  size: count,
  change,
}: {
  page: number;
  total: number;
  size: number;
  change: (n: number) => void;
}) {
  if (total <= count) return null;
  const pages = Math.ceil(total / count);
  return (
    <div className="pagination">
      <span>
        Page {page} of {pages}
      </span>
      <button className="button small" disabled={page === 1} onClick={() => change(page - 1)}>
        <ArrowLeft size={15} />
        Previous
      </button>
      <button className="button small" disabled={page === pages} onClick={() => change(page + 1)}>
        Next
        <ArrowRight size={15} />
      </button>
    </div>
  );
}
function SettingsForm({
  initial,
  apply,
}: {
  initial: AuditSettings;
  apply: (s: AuditSettings) => void;
}) {
  const [next, setNext] = useState(initial);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        apply(next);
      }}
      className="settings-form"
    >
      <p>
        Quality measurements use a normalized 128 × 128 image. These are review heuristics, not a
        pass/fail certificate.
      </p>
      {(
        [
          {
            key: 'similarity',
            label: 'Similarity distance',
            min: 0,
            max: 12,
            step: 1,
            note: 'Maximum differing bits in the 64-bit dHash. Lower is stricter.',
          },
          {
            key: 'blur',
            label: 'Sharpness threshold',
            min: 0,
            max: 500,
            step: 5,
            note: 'Flag Laplacian variance below this value. Textureless images can also trigger it.',
          },
          {
            key: 'dark',
            label: 'Darkness threshold',
            min: 0,
            max: 100,
            step: 1,
            note: 'Flag mean brightness below this value (0–255).',
          },
          {
            key: 'bright',
            label: 'Brightness threshold',
            min: 155,
            max: 255,
            step: 1,
            note: 'Flag mean brightness above this value (0–255).',
          },
          {
            key: 'minSize',
            label: 'Minimum shortest side',
            min: 0,
            max: 1024,
            step: 16,
            note: 'Flag images whose shortest side is smaller than this many pixels.',
          },
        ] as {
          key: keyof AuditSettings;
          label: string;
          min: number;
          max: number;
          step: number;
          note: string;
        }[]
      ).map((x) => (
        <label key={x.key}>
          <span>
            {x.label}
            <output>{next[x.key]}</output>
          </span>
          <input
            aria-label={x.label}
            type="range"
            min={x.min}
            max={x.max}
            step={x.step}
            value={next[x.key]}
            onChange={(e) => setNext({ ...next, [x.key]: Number(e.target.value) })}
          />
          <small>{x.note}</small>
        </label>
      ))}
      <div className="modal-footer">
        <button type="button" className="text-button" onClick={() => setNext(DEFAULT_SETTINGS)}>
          Restore defaults
        </button>
        <button className="button primary" type="submit">
          Apply settings
          <Check size={16} />
        </button>
      </div>
    </form>
  );
}
function Guide({ loadDemo }: { loadDemo: () => void }) {
  return (
    <div className="guide">
      <section>
        <div className="small-label">01 / BRING YOUR IMAGES</div>
        <h2>Folder structure tells the story.</h2>
        <p>
          Import a folder or ZIP to preserve split information. SplitLens recognizes train /
          training, val / valid / validation, and test / testing as folder segments. Files without a
          recognized split are unassigned; you can correct them in Image library.
        </p>
        <pre>
          my-dataset/{'\n'} train/bottle/image-001.jpg{'\n'} val/bottle/image-002.jpg{'\n'}{' '}
          test/cup/image-003.png
        </pre>
        <p>
          JPEG, PNG, WebP, AVIF, and BMP are supported where the browser can decode them. Maximum
          1,500 images, 300 MB total, and 30 MB per file. SVG and animated formats are excluded.
        </p>
      </section>
      <section>
        <div className="small-label">02 / INSPECT THE EVIDENCE</div>
        <h2>Fast checks. Transparent limits.</h2>
        <p>
          <strong>Exact duplicates:</strong> SHA-256 over file bytes.{' '}
          <strong>Similar images:</strong> a 64-bit difference hash with aspect-ratio and brightness
          checks. Cross-split matches are flagged as potential leakage. These checks detect simple
          duplicates; crops, rotations, semantic similarity, and subject-level leakage can be
          missed.
        </p>
        <p>
          <strong>Image quality:</strong> mean brightness, Laplacian variance for sharpness,
          resolution, and decoding failures. Quality thresholds are configurable and depend on your
          domain. Low sharpness can also mean a smooth background. Always inspect the images.
        </p>
        <p>
          The sample dataset is procedurally generated and analyzed live. Its defects are
          intentional. No model weights, image uploads, analytics, or external font requests are
          involved.
        </p>
      </section>
      <section>
        <div className="small-label">03 / MAKE YOUR DECISION</div>
        <h2>Nothing is removed automatically.</h2>
        <p>
          Open a finding and mark each image Keep or Exclude. Exports include unreviewed images. The
          curated ZIP excludes only your explicit exclusions, retains original file bytes and folder
          paths, and includes a decision manifest.
        </p>
        <p>
          Audits live in memory for this session. Reloading clears your imported dataset and
          decisions. Download a report before leaving. The visual HTML report includes thumbnails;
          JSON and CSV include filenames and metadata.
        </p>
        <button className="button secondary" onClick={loadDemo}>
          <Sparkles size={16} />
          Explore demo
        </button>
      </section>
    </div>
  );
}
