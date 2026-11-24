import { isAxiosError } from 'axios';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { teacherApi, type AnswerSheetTemplateItem, type ExamSource, type PaperDraft, type PaperDraftInput } from '../../api/teacher';
import { Icon, Select, Sheet, errorText } from '../mobileControls';
import { ExamSourcePreview, SourceCard } from './ExamSources';
import { DesktopPaperGrading, usePaperGrading } from './PaperGradingStatus';
import { FixedCardGuide } from './FixedCardGuide';
import {
  paperCreationKey, readPaperCreation, writePaperCreation, type PendingPaperCreation, type SelectedPaperTemplate,
} from './paperCreationRecovery';

interface TemplateCreatorProps {
  onCancel: () => void;
  onSaved: (template: AnswerSheetTemplateItem) => void;
}

function uploadFailureText(failure: unknown) {
  if (isAxiosError(failure) && failure.code === 'ERR_NETWORK') return '网络中断，已上传的文件已保留。';
  return errorText(failure);
}

export function PaperDraftEditor({ desktop = false, renderTemplateCreator }: {
  desktop?: boolean;
  renderTemplateCreator?: (props: TemplateCreatorProps) => ReactNode;
}) {
  const { examId } = useParams();
  const { state: locationState } = useLocation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const recoveryKey = examId ? undefined : paperCreationKey(desktop);
  const [recovery] = useState(() => readPaperCreation(recoveryKey));
  const resumeId = recovery && 'examId' in recovery ? recovery.examId : undefined;
  const pendingCreation = recovery && 'requestId' in recovery ? recovery : undefined;
  const initialForm = pendingCreation?.editing ?? pendingCreation;
  const initialStep = examId && !desktop ? params.get('step') : null;
  const firstStep = initialStep === 'template' ? 1 : initialStep === 'answers' ? 2 : 0;
  const [step, setStep] = useState(initialForm?.step ?? firstStep);
  const [title, setTitle] = useState(initialForm?.input.title ?? '');
  const [description, setDescription] = useState(initialForm?.input.description ?? '');
  const [classId, setClassId] = useState(initialForm?.input.class_id === '0' ? '' : initialForm?.input.class_id ?? '');
  const [classes, setClasses] = useState<Awaited<ReturnType<typeof teacherApi.listClasses>>>([]);
  const [templates, setTemplates] = useState<AnswerSheetTemplateItem[]>([]);
  const [selected, setSelected] = useState<SelectedPaperTemplate | undefined>(initialForm?.template);
  const [pendingTemplate, setPendingTemplate] = useState<AnswerSheetTemplateItem>();
  const [candidate, setCandidate] = useState<AnswerSheetTemplateItem>();
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const [snapshot, setSnapshot] = useState<PaperDraft>();
  const [answers, setAnswers] = useState<Record<number, string>>(() => {
    if (pendingCreation?.editing || !initialForm?.input.question_numbers) return initialForm?.input.answers ?? {};
    return Object.fromEntries(initialForm.input.question_numbers.map((number, index) => [
      index + 1, initialForm.input.answers[number] ?? '',
    ]));
  });
  const [cardNumbers, setCardNumbers] = useState<Record<number, string>>(() =>
    initialForm?.cardNumbers ?? Object.fromEntries((initialForm?.input.question_numbers ?? []).map(
      (number, index) => [index + 1, String(number)],
    )),
  );
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(Boolean(examId));
  const [dirty, setDirty] = useState(Boolean(pendingCreation));
  const [leaveTo, setLeaveTo] = useState<string>();
  const [sources, setSources] = useState<ExamSource[]>([]);
  const [sourcePreview, setSourcePreview] = useState<ExamSource>();
  const [failed, setFailed] = useState<{ file: File; error: string }[]>([]);
  const [sourceError, setSourceError] = useState('');
  const [uploading, setUploading] = useState('');
  const [removing, setRemoving] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const creation = useRef<PendingPaperCreation | undefined>(pendingCreation);
  const draftId = snapshot?.id ?? examId;
  const desktopGrading = usePaperGrading(desktop && snapshot?.paper_draft ? draftId : undefined);
  const destination = !desktop && draftId ? `/exams/${draftId}` : '/exams';

  useEffect(() => {
    if (!resumeId || examId) return;
    writePaperCreation(recoveryKey);
    navigate(desktop ? `/exams/paper-drafts/${resumeId}` : `/exams/${resumeId}/edit`, { replace: true, state: locationState });
  }, [desktop, examId, locationState, navigate, recoveryKey, resumeId]);

  useEffect(() => {
    const attempt = creation.current;
    if (!attempt || draftId) return;
    writePaperCreation(recoveryKey, {
      ...attempt, editing: { step, template: selected, cardNumbers, input: {
        title, description, class_id: classId || '0', answers,
      } },
    });
  }, [answers, cardNumbers, classId, description, draftId, recoveryKey, selected, step, title]);

  useEffect(() => {
    let live = true;
    void Promise.all([teacherApi.listClasses(), teacherApi.listAnswerSheetTemplates({ paperOnly: true })]).then(([roster, items]) => {
      if (live) { setClasses(roster); setTemplates(items); }
    }).catch(failure => { if (live) setError(errorText(failure)); });
    return () => { live = false; };
  }, []);
  useEffect(() => {
    if (!examId) return;
    const controller = new AbortController();
    void teacherApi.getPaperDraft(examId, controller.signal).then(draft => {
      if (controller.signal.aborted) return;
      setSnapshot(draft);
      setTitle(draft.title);
      setDescription(draft.description);
      setClassId(draft.class_id === '0' ? '' : draft.class_id);
      setCardNumbers({});
      setAnswers(Object.fromEntries(draft.questions.map(question => [question.question_number, question.answer])));
      if (initialStep === 'answers' && !draft.questions.length) setStep(1);
    }).catch(failure => { if (!controller.signal.aborted) setError(errorText(failure)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [examId, initialStep]);
  useEffect(() => {
    if (!examId) return;
    const controller = new AbortController();
    void teacherApi.listExamSources(examId, controller.signal).then(items => {
      if (!controller.signal.aborted) setSources(items);
    }).catch(failure => { if (!controller.signal.aborted) setSourceError(errorText(failure)); });
    return () => controller.abort();
  }, [examId]);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ''; };
    window.addEventListener('beforeunload', beforeUnload);
    return () => window.removeEventListener('beforeunload', beforeUnload);
  }, [dirty]);

  const questions = selected ? selected.choice_questions.map((question, index) => ({
    question_number: index + 1, score: question.score,
    options: Array.from({ length: question.option_count || question.options?.length || 0 }, (_, option) => String.fromCharCode(65 + option)),
  })) : snapshot?.questions ?? [];
  const questionNumbers = questions.map(question => Number(cardNumbers[question.question_number] ?? question.question_number));
  const validQuestionNumbers = questionNumbers.every(number => Number.isSafeInteger(number) && number > 0) &&
    new Set(questionNumbers).size === questionNumbers.length;
  const currentName = selected?.name || snapshot?.template_name || (questions.length ? '已保存的评分配置' : '');
  const candidateItem = candidate ?? templates.find(item => item.id === (selected?.id ?? snapshot?.template_id));
  const answered = questions.filter(question => answers[question.question_number]).length;
  const missingAnswers = questionNumbers.filter((_, index) => !answers[questions[index].question_number]);
  const savingUnavailable = saving || Boolean(uploading) || removing || !title.trim() || !validQuestionNumbers;
  const canFinalize = !savingUnavailable && sources.length > 0 && questions.length > 0 && answered === questions.length;
  const arrangeTemplate = (item: AnswerSheetTemplateItem) => {
    const id = selected ? String(selected.id) : snapshot?.template_id;
    const revision = selected?.revision ?? snapshot?.template_revision;
    if (String(item.id) === id && item.revision === revision) { setStep(2); return; }
    if (answered) {
      setPendingTemplate(item);
      setStep(2);
    }
    else applyTemplate(item);
  };
  const applyTemplate = (item: AnswerSheetTemplateItem) => {
    setSelected(item);
    setCardNumbers({});
    setAnswers({});
    setDirty(true);
    setPendingTemplate(undefined);
    setStep(2);
  };

  function leaveEditor(path: string) {
    if (dirty) setLeaveTo(path);
    else discardLocalCreation(path);
  }

  function discardLocalCreation(path: string) {
    writePaperCreation(recoveryKey);
    navigate(path, { state: locationState });
  }

  async function save(afterSave?: string, finalize = false) {
    if (savingUnavailable || (examId && !snapshot)) return;
    setSaving(true);
    setError('');
    try {
      const result = await persist(finalize);
      writePaperCreation(recoveryKey);
      setDirty(false);
      navigate(afterSave ?? (desktop ? '/exams' : `/exams/${result.id}`), { replace: true, state: locationState });
    } catch (failure) {
      setError(errorText(failure));
    } finally {
      setSaving(false);
    }
  }

  async function persist(finalize = false) {
    if (!validQuestionNumbers) throw new Error('每道题必须绑定一个不同的卡面题号');
    const input: PaperDraftInput = {
      title: title.trim(), description, class_id: classId || '0',
      answers: Object.fromEntries(questions.flatMap((question, index) => (
        question.question_number in answers ? [[questionNumbers[index], answers[question.question_number]]] : []
      ))),
      revision: snapshot?.revision, template_id: selected && String(selected.id), template_revision: selected?.revision, finalize,
    };
    if (questions.some((question, index) => question.question_number !== questionNumbers[index])) {
      input.question_numbers = questionNumbers;
    }
    if (draftId) return teacherApi.savePaperDraft(input, draftId);

    const attempt = creation.current ??= { requestId: crypto.randomUUID(), input, step, template: selected };
    writePaperCreation(recoveryKey, { ...attempt, editing: {
      input: { ...input, answers, question_numbers: undefined }, step, template: selected, cardNumbers,
    } });
    let created: PaperDraft;
    try {
      created = await teacherApi.savePaperDraft({ ...attempt.input, request_id: attempt.requestId });
    } catch (failure) {
      const status = isAxiosError(failure) && failure.response?.status;
      if (status && status >= 400 && status < 500 && status !== 408 && status !== 429) {
        creation.current = undefined;
        writePaperCreation(recoveryKey);
      }
      throw failure;
    }
    creation.current = undefined;
    writePaperCreation(recoveryKey, { examId: created.id });
    if (JSON.stringify(attempt.input) === JSON.stringify(input)) return created;

    // Recover the original creation before applying edits made after the failed response.
    const revision = created.created_revision ?? created.revision;
    setSnapshot({ ...created, revision });
    return teacherApi.savePaperDraft({ ...input, revision }, created.id);
  }

  async function upload(files: File[]) {
    if (!files.length || uploading || saving || removing || !title.trim()) return;
    setUploading(files[0].name);
    setSourceError('');
    setFailed(previous => previous.filter(item => !files.includes(item.file)));
    let target = draftId;
    try {
      if (!target || !snapshot?.paper_draft) {
        const created = await persist();
        setSnapshot(created);
        setTitle(created.title);
        setDescription(created.description);
        setClassId(created.class_id === '0' ? '' : created.class_id);
        setCardNumbers({});
        setAnswers(Object.fromEntries(created.questions.map(question => [question.question_number, question.answer])));
        setSelected(undefined);
        setDirty(false);
        target = created.id;
      }
      for (const file of files) {
        setUploading(file.name);
        try {
          const uploaded = await teacherApi.uploadExamSource(target, file);
          setSources(previous => [...previous.filter(source => source.id !== uploaded.id), uploaded].sort((a, b) => a.order - b.order));
        } catch (failure) {
          setFailed(previous => [...previous, { file, error: uploadFailureText(failure) }]);
        }
      }
      if (desktop) desktopGrading.retry();
    } catch (failure) {
      setDirty(true);
      setFailed(previous => [...previous, ...files.map(file => ({ file, error: uploadFailureText(failure) }))]);
    } finally {
      setUploading('');
    }
  }

  async function remove(source: ExamSource) {
    if (!draftId || removing || uploading) return;
    setRemoving(true);
    setSourceError('');
    try {
      await teacherApi.removeExamSource(draftId, source.id);
      setSources(previous => previous.filter(item => item.id !== source.id));
      if (desktop) desktopGrading.retry();
    } catch (failure) {
      setSourceError(errorText(failure));
    } finally {
      setRemoving(false);
    }
  }

  if (guideOpen) return <FixedCardGuide examId={snapshot?.paper_draft ? draftId : undefined}
    desktop={desktop} onBack={() => setGuideOpen(false)} />;

  if (creatingTemplate && renderTemplateCreator) return renderTemplateCreator({
    onCancel: () => setCreatingTemplate(false),
    onSaved: item => {
      setCreatingTemplate(false);
      setTemplates(previous => [item, ...previous]);
      setCandidate(item);
      arrangeTemplate(item);
    },
  });
  return <div className="paper-draft-editor">
    <header className="heading"><button type="button" className="round" aria-label="返回" disabled={Boolean(uploading) || saving || removing} onClick={() => {
      if (renderTemplateCreator && step > firstStep) setStep(step - 1);
      else leaveEditor(destination);
    }}><Icon name="left" /></button><h1>{['填写试卷资料', renderTemplateCreator ? '选择评分模板' : '选择模板', '设置本卷答案'][step]}</h1></header>
    {desktop && draftId && snapshot && <nav className="web-paper-draft-links" aria-label="纸质批改">
      <button className="secondary" disabled={Boolean(uploading) || saving || removing} onClick={() => leaveEditor(`/exams/${draftId}/records`)}>批改记录</button>
      {snapshot.paper_draft && <button className="secondary" disabled={Boolean(uploading) || saving || removing}
        onClick={() => leaveEditor(`/exams/${draftId}/rules`)}>评分规则与本卷答案</button>}
      <button type="button" className="secondary" disabled={savingUnavailable} onClick={() => setGuideOpen(true)}>固定版式答题卡</button>
      <button className="secondary" disabled={Boolean(uploading) || saving || removing ||
        !desktopGrading.status?.recognition_available || desktopGrading.status.state === 'completed'}
        onClick={() => leaveEditor(`/exams/${draftId}/scan`)}>拍摄答题卡</button>
      <button className="secondary" disabled={Boolean(uploading) || saving || removing} onClick={() => leaveEditor(`/exams/${draftId}/scan/reviews`)}>待复核答题卡</button>
    </nav>}
    {desktop && snapshot?.paper_draft && draftId && <DesktopPaperGrading key={draftId} examId={draftId} grading={desktopGrading} />}
    {(resumeId || loading || (examId && !snapshot)) ? <p className={`notice ${error ? 'failure' : ''}`}>{error || '正在加载…'}</p> : <>
    <div className="stepper">{['试卷资料', '评分模板', '本卷答案'].map((item, index) => <span className={step === index ? 'current' : index < step ? 'completed' : ''} key={item}>{item}</span>)}</div>
    <form className="editor exam-editor" onSubmit={event => {
      event.preventDefault();
      if (step === 0 && !savingUnavailable && !failed.length) setStep(currentName ? 2 : 1);
    }}>
      {step === 0 && <>
        <label>试卷名称<span className="draft-entry"><Icon name="files" size={18} /><input required placeholder="输入试卷名称" maxLength={256} value={title} onChange={event => { setTitle(event.target.value); setDirty(true); }} /></span></label>
        <div className="editor-field">班级（选填）<Select label="班级（选填）" value={classId} onChange={value => { setClassId(value); setDirty(true); }}
          options={[...classes.map(item => ({ value: String(item.id), label: item.name })), { value: '', label: '未关联班级' }]} /></div>
        <label>备注 · 选填<span className="draft-entry"><Icon name="bubble" size={18} /><input placeholder="请输入备注" maxLength={512} value={description} onChange={event => { setDescription(event.target.value); setDirty(true); }} /></span></label>
        <h2>试卷原件</h2>
        {sources.map(source => <SourceCard source={source} key={source.id} locked={Boolean(uploading) || removing}
          onClick={() => setSourcePreview(source)} onRemove={() => void remove(source)} />)}
        <input type="file" hidden ref={picker} accept=".pdf,.docx,.jpg,.jpeg,.png,.webp" multiple
          onChange={event => { const files = Array.from(event.target.files ?? []); event.target.value = ''; void upload(files); }} />
        <button type="button" className="secondary" disabled={!title.trim() || Boolean(uploading) || saving || removing} onClick={() => picker.current?.click()}>
          {uploading ? '正在上传…' : '添加文档或图片'}
        </button>
        <small className="source-hint">支持 PDF、DOCX、JPEG、PNG、WebP。</small>
        {uploading && <p className="caption" aria-live="polite">{uploading}</p>}
        {sourceError && <p className="notice failure" role="alert">{sourceError}</p>}
        {failed.map((item, index) => <div className="source-failure notice warning" key={index} role="alert">
          <Icon name="warning" size={19} />
          <div><strong>{item.file.type.startsWith('image/') ? '图片上传失败' : '文档上传失败'}</strong>
            <small>{failed.length > 1 ? `${item.file.name} · ` : ''}{item.error}</small></div>
          <button type="button" className="plain" aria-label={`移除失败文件 ${item.file.name}`} disabled={Boolean(uploading)} onClick={() => setFailed(previous => previous.filter(entry => entry !== item))}><Icon name="close" size={18} /></button>
        </div>)}
      </>}
      {step === 1 && <div className={`card-list ${renderTemplateCreator ? 'draft-template-picker' : ''}`}>
        {templates.length ? templates.map(item => {
          const checked = item.id === candidateItem?.id;
          return <button type="button" className={`list-card template-choice ${checked ? 'selected' : ''}`} key={item.id}
            aria-pressed={checked} onClick={() => renderTemplateCreator ? setCandidate(item) : arrangeTemplate(item)}>
            {renderTemplateCreator && <span className="template-icon"><Icon name="template" /></span>}
            <span><strong>{item.name}</strong><small>{item.question_count} 题 · 满分 {item.total_score} 分</small></span>
            {renderTemplateCreator && <span className="template-radio">{checked && <Icon name="check" size={12} />}</span>}
          </button>;
        }) : <p className="notice">暂无模板</p>}
      </div>}
      {step === 2 && <>
        <div className="draft-answer-summary"><div><strong>{currentName}</strong><small>已配置 {answered} / {questions.length} 题 · 满分 {questions.reduce((sum, question) => sum + question.score, 0)} 分</small></div><button type="button" className="plain" onClick={() => setStep(1)}>更换</button></div>
        {questions.map(item => <fieldset key={item.question_number} className="draft-answer">
          <legend><label>卡面题号 <input type="text" inputMode="numeric" size={4} maxLength={16}
            aria-label={`第 ${item.question_number} 行的卡面题号`}
            value={cardNumbers[item.question_number] ?? item.question_number}
            onChange={event => {
              const value = event.target.value;
              if (!/^\d*$/.test(value)) return;
              setCardNumbers(previous => ({ ...previous, [item.question_number]: value }));
              setDirty(true);
            }} /></label><span>{item.score} 分</span></legend>
          <div className="draft-options">{item.options.map(option => <button key={option} type="button" className="secondary" aria-pressed={answers[item.question_number] === option} aria-label={`第 ${cardNumbers[item.question_number] ?? item.question_number} 题 ${option}`}
            onClick={() => { setAnswers(previous => ({ ...previous, [item.question_number]: previous[item.question_number] === option ? '' : option })); setDirty(true); }}>{option}</button>)}</div>
        </fieldset>)}
        {!validQuestionNumbers && <p className="notice warning" role="status">每道题必须绑定一个不同的卡面题号。</p>}
        {validQuestionNumbers && missingAnswers.length > 0 && <p className="draft-answer-missing" role="status">第 {missingAnswers.slice(0, 8).join('、')}{missingAnswers.length > 8 ? '…' : ''} 题还没有设置标准答案。</p>}
        {snapshot?.layout_configured === false && <p className="notice warning">固定答题卡版式未配置，保存草稿后可继续编辑。</p>}
        {!sources.length && <p className="notice warning">请先添加试卷原件</p>}
      </>}
      {error && <p className="notice failure" role="alert">{error}</p>}
      {step === 1 && renderTemplateCreator ? <div className="actions footer-actions">
        <button type="button" className="secondary" onClick={() => setCreatingTemplate(true)}>新建模板</button>
        <button type="button" className="primary" disabled={!candidateItem} onClick={() => { if (candidateItem) arrangeTemplate(candidateItem); }}>下一步</button>
      </div> : step === 2 ? <div className="actions footer-actions">
        <button type="button" className="secondary" disabled={savingUnavailable} onClick={() => void save()}>保存草稿</button>
        {snapshot?.layout_configured === false && !missingAnswers.length && questions.length > 0
          ? <button type="button" className="primary" disabled={saving || Boolean(uploading) || removing} onClick={() => setGuideOpen(true)}>查看答题卡说明</button>
          : <button type="button" className="primary draft-finalize" disabled={!canFinalize || snapshot?.layout_configured === false}
              onClick={() => void save(undefined, true)}>{saving ? '正在保存…' : '保存试卷'}</button>}
      </div> : <div className="actions footer-actions">
        {step > 0 && <button type="button" className="secondary" onClick={() => setStep(step - 1)}>上一步</button>}
        <button type="button" className="secondary" disabled={savingUnavailable} onClick={() => void save()}>{saving ? '正在保存…' : '保存草稿'}</button>
        {step === 0 && (failed.length
          ? <button type="button" className="primary" disabled={savingUnavailable} onClick={() => void upload(failed.map(item => item.file))}>重试上传</button>
          : <button className="primary" disabled={savingUnavailable}>下一步</button>)}
      </div>}
    </form>
    </>}
    {pendingTemplate && <Sheet title="更换评分模板？" variant="draft" close={() => setPendingTemplate(undefined)}>
      <p className="caption">{pendingTemplate.question_count} 题 · {pendingTemplate.total_score} 分，更换后需重新设置答案。</p>
      <div className="actions"><button className="secondary" onClick={() => { setPendingTemplate(undefined); setStep(2); }}>保留旧模板</button><button className="primary" onClick={() => applyTemplate(pendingTemplate)}>更换模板</button></div>
    </Sheet>}
    {leaveTo && <Sheet title="保存本次修改？" variant="draft" close={() => { if (!saving) setLeaveTo(undefined); }}>
      <button className="plain draft-discard" disabled={saving} onClick={() => discardLocalCreation(leaveTo)}>放弃修改</button>
      {error && <p className="notice failure" role="alert">{error}</p>}
      <div className="actions"><button className="secondary" disabled={saving} onClick={() => setLeaveTo(undefined)}>继续编辑</button><button className="primary" disabled={saving || !title.trim()} onClick={() => void save(leaveTo)}>{saving ? '正在保存…' : '保存草稿'}</button></div>
    </Sheet>}
    {sourcePreview && draftId && <ExamSourcePreview key={sourcePreview.id} examId={draftId} source={sourcePreview} close={() => setSourcePreview(undefined)} />}
  </div>;
}
