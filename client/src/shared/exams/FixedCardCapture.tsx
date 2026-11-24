import { useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { teacherApi } from '../../api/teacher';
import { usePaperGrading } from './PaperGradingStatus';
import { Icon, Sheet, errorText } from '../mobileControls';
import illustration from './assets/fixed-card-illustration.png';

export function FixedCardCapture({ desktop = false }: { desktop?: boolean } = {}) {
  const { examId = '' } = useParams();
  return <CaptureDetail key={examId} examId={examId} desktop={desktop} />;
}

function CaptureDetail({ examId, desktop }: { examId: string; desktop: boolean }) {
  const navigate = useNavigate();
  const grading = usePaperGrading(examId);
  const root = `/exams/${examId}`;
  const back = desktop ? `/exams/paper-drafts/${examId}` : root;
  const completed = grading.status?.state === 'completed';
  const [camera, setCamera] = useState(false);
  const [ready, setReady] = useState(false);
  const [guideSize, setGuideSize] = useState<{ width: number; height: number }>();
  const [taking, setTaking] = useState(false);
  const [cameraFailed, setCameraFailed] = useState(false);
  const [photo, setPhoto] = useState<File | Blob>();
  const [preview, setPreview] = useState('');
  const [error, setError] = useState('');
  const [failed, setFailed] = useState<'retake' | 'layout_mismatch'>();
  const [working, setWorking] = useState(false);
  const request = useRef<AbortController>();
  const requestId = useRef('');
  useEffect(() => () => request.current?.abort(), []);
  const video = useRef<HTMLVideoElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const captureRatio = grading.status?.capture_aspect_ratio;

  useEffect(() => {
    const element = video.current;
    if (!camera || !element || !captureRatio) return;
    function resizeGuide() {
      if (!element?.videoWidth || !element.videoHeight || !captureRatio) return;
      const scale = Math.min(element.clientWidth / element.videoWidth, element.clientHeight / element.videoHeight);
      const height = 0.92 * scale * Math.min(element.videoHeight, element.videoWidth / captureRatio);
      setGuideSize({ width: height * captureRatio, height });
    }
    const observer = new ResizeObserver(resizeGuide);
    observer.observe(element);
    element.addEventListener('resize', resizeGuide);
    resizeGuide();
    return () => {
      observer.disconnect();
      element.removeEventListener('resize', resizeGuide);
    };
  }, [camera, captureRatio, ready]);

  useEffect(() => {
    if (!camera) return;
    let live = true;
    let stream: MediaStream | undefined;
    function stop() {
      stream?.getTracks().forEach(track => {
        track.removeEventListener('ended', onEnded);
        track.stop();
      });
    }
    function onEnded() {
      if (live) {
        setReady(false);
        setTaking(false);
        setCamera(false);
        setCameraFailed(true);
      }
    }
    function onHidden() {
      if (document.hidden) {
        live = false;
        stop();
        setCamera(false);
        setReady(false);
        setTaking(false);
      }
    }
    document.addEventListener('visibilitychange', onHidden);
    async function openCamera() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false });
        if (!live || !video.current) {
          stop();
          return;
        }
        stream.getVideoTracks().forEach(track => track.addEventListener('ended', onEnded));
        video.current.srcObject = stream;
        await video.current.play();
      } catch {
        onEnded();
      }
    }
    void openCamera();
    return () => {
      live = false;
      document.removeEventListener('visibilitychange', onHidden);
      stop();
    };
  }, [camera]);

  useEffect(() => {
    if (!photo) { setPreview(''); return; }
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  function openCamera() {
    setError('');
    setFailed(undefined);
    setCameraFailed(false);
    setReady(false);
    setTaking(false);
    setGuideSize(undefined);
    setCamera(true);
  }

  function choosePhoto(file?: File) {
    if (!file) return;
    if (file.size > 12 * 1024 * 1024 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      setError('请选择不超过 12 MiB 的 JPEG、PNG 或 WebP 图片');
      return;
    }
    setCamera(false);
    setTaking(false);
    setError('');
    setFailed(undefined);
    requestId.current = '';
    setPhoto(file);
  }

  function capture() {
    const element = video.current;
    if (!element?.videoWidth || taking) return;
    const canvas = document.createElement('canvas');
    canvas.width = element.videoWidth;
    canvas.height = element.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.drawImage(element, 0, 0);
    setTaking(true);
    canvas.toBlob(blob => {
      if (video.current !== element || document.hidden) return;
      setTaking(false);
      if (!blob || blob.size > 12 * 1024 * 1024) {
        setError('拍照失败，请重试');
        return;
      }
      requestId.current = '';
      setPhoto(blob);
      setCamera(false);
    }, 'image/jpeg', 0.92);
  }

  async function submit() {
    if (!photo || request.current || completed || !grading.status?.recognition_available) return;
    const abort = new AbortController();
    request.current = abort;
    setWorking(true);
    setError('');
    try {
      requestId.current ||= crypto.randomUUID();
      const result = await teacherApi.recognizeFixedCard(examId, photo, requestId.current, abort.signal);
      if (abort.signal.aborted) return;
      if (result.state === 'review') navigate(`${root}/scan/reviews/${result.scan_id}`, { state: { fromCapture: true } });
      else setFailed(result.state);
    } catch (failure) {
      if (!abort.signal.aborted) setError(errorText(failure));
    } finally {
      if (!abort.signal.aborted) setWorking(false);
      request.current = undefined;
    }
  }

  function retake() {
    setPhoto(undefined);
    openCamera();
  }

  const title = working ? '正在识别' : failed === 'layout_mismatch' ? '版式不匹配' : failed ? '需要重拍'
    : camera ? '拍摄答题卡' : photo ? '检查照片' : '开始批卷';
  const unavailable = completed ? '批卷已结束，请先开启补批' : grading.status && !grading.status.recognition_available
    ? grading.status.recognition_blocker || '固定答题卡版式未配置' : '';
  const available = Boolean(grading.status && !unavailable);
  return <section className="scan-page scan-capture">
    <header className="heading"><Link className="round" to={back} aria-label="返回"><Icon name="left" /></Link><h1>{title}</h1></header>
    {grading.status && <p className="review-subtitle">{[grading.status.exam_title, grading.status.class_name || '无关联班级'].filter(Boolean).join(' · ')}</p>}
    <input type="file" hidden accept="image/jpeg,image/png,image/webp" ref={picker} onChange={event => { choosePhoto(event.target.files?.[0]); event.target.value = ''; }} />
    {camera || photo ? <div className="viewfinder" data-retake={failed === 'retake'}>
      <div className="scan-corners" data-layout-guide={camera && !!guideSize}
        style={camera && guideSize ? {
          '--card-guide-width': `${guideSize.width}px`, '--card-guide-height': `${guideSize.height}px`,
        } as CSSProperties : undefined}>
        {camera ? <video ref={video} autoPlay muted playsInline onCanPlay={() => setReady(true)} />
          : preview && <img src={preview} alt="已选答题卡照片" onError={() => { setPhoto(undefined); setError('无法读取图片，请重新选择'); }} />}
        {failed === 'retake' && <span className="scan-retake-symbol"><Icon name="warning" size={42} /></span>}
      </div>
      {!working && !failed && <p>{camera ? '姓名、考号和填涂区一同入框' : '确认四角完整，考号清晰'}</p>}
    </div> : <div className="scan-guide">
      <div><img src={illustration} alt="固定答题卡示意" /></div>
      <p>将指定答题卡完整放入取景框。</p>
    </div>}
    {working && <div className="scan-recognition" role="status"><Icon name="scan" size={28} /><p>正在识别考号和每题填涂…</p></div>}
    {failed && <div className="scan-failure" role="alert" data-state={failed}>
      <Icon name="warning" size={19} />
      <div><strong>{failed === 'layout_mismatch' ? '答题卡版式不匹配' : '未能识别答题卡版式'}</strong>
        <p>{failed === 'layout_mismatch' ? '请换用指定的固定版式答题卡。' : '把整张卡放平，移开遮挡，再重拍一张。'}</p></div>
    </div>}
    {error && <p className="notice failure" role="alert">{error}</p>}
    {grading.error && <p className="notice failure" role="alert">{grading.error} <button className="plain" onClick={grading.retry}>重试</button></p>}
    {!!unavailable && !camera && <p className="notice warning">{unavailable}</p>}
    {!camera && !photo && !!grading.status?.pending && <Link className="list-card review-entry scan-pending" to={`${root}/scan/reviews`} state={{ fromCapture: true }}>
      <Icon name="files" /><span>待复核答题卡</span><Icon name="right" size={17} />
    </Link>}
    {camera ? <div className="scan-controls">
      <button className="plain scan-album" disabled={taking} onClick={() => picker.current?.click()}><span><Icon name="image" /></span>相册</button>
      <button className="plain scan-shutter" disabled={!ready || taking || !available} onClick={capture}><span><Icon name="camera" size={26} /></span>拍照</button>
      <div className="scan-count"><strong>{grading.status?.confirmed ?? 0} 份</strong><small>已确认</small></div>
    </div> : !working && <div className="actions scan-actions">
      {failed ? <>
        {failed === 'layout_mismatch' ? <Link className="secondary" to={back}>返回试卷</Link>
          : <button className="secondary" onClick={() => picker.current?.click()}>选取照片</button>}
        <button className="primary" disabled={!available} onClick={retake}>重新拍摄</button>
      </> : photo ? <>
        <button className="secondary" onClick={retake}>重拍</button>
        <button className="primary" disabled={!available} onClick={() => void submit()}>识别答题卡</button>
      </> : <>
        <button className="secondary" disabled={!available} onClick={() => picker.current?.click()}>从相册选择</button>
        <button className="primary" disabled={!available} onClick={openCamera}>打开相机</button>
      </>}
    </div>}
    {cameraFailed && <Sheet title="相机暂不可用" variant="camera-permission" icon="cameraOff" portalClassName={desktop ? 'web-paper-draft web-paper-grading exam-grading paper-review-portal' : undefined} close={() => setCameraFailed(false)}>
      <p>在浏览器设置中允许相机权限。</p>
      <div className="actions"><button className="secondary" onClick={openCamera}>重新尝试</button><button className="primary" onClick={() => { setCameraFailed(false); picker.current?.click(); }}>从相册选择</button></div>
    </Sheet>}
  </section>;
}
