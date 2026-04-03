(function() {
function $(sel) { return document.querySelector(sel); }

let state = {
  pdfId: null,
  pageCount: 0,
  currentPage: 0,
  sigPath: null,
  sigPath: null,
  originalFilename: "",
  containerMeta: { width: 0, height: 0 },
  imgNatural: { width: 0, height: 0 }
};

// ── File Upload Handlers ──────────────────────────────────────────────────

$('#pdf-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  
  $('#pdf-name').textContent = file.name;
  $('#pdf-upload-wrap').classList.add('has-file');
  state.originalFilename = file.name;
  
  const formData = new FormData();
  formData.append('file', file);
  
  setStatus('Uploading PDF...');
  try {
    const res = await fetch('/api/pdf/upload_raw', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    
    state.pdfId = data.pdf_id;
    state.pageCount = data.pages;
    state.currentPage = 0;
    
    await loadPageImage();
    $('#empty-state').style.display = 'none';
    $('#pdf-container').style.display = 'block';
    setStatus('');
    checkReady();
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  }
});

$('#sig-file').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  
  $('#sig-name').textContent = file.name;
  $('#sig-upload-wrap').classList.add('has-file');
  
  const formData = new FormData();
  formData.append('file', file);
  
  setStatus('Uploading Signature...');
  try {
    const res = await fetch('/api/upload-signature', { method: 'POST', body: formData });
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    
    state.sigPath = data.path;
    
    // Set image in UI
    const sigImg = $('#sig-img');
    const el = $('#signature-element');
    
    // Create an object URL just for local preview to avoid path routing issues on frontend
    const url = URL.createObjectURL(file);
    sigImg.src = url;
    
    sigImg.onload = () => {
      // Set reasonable initial size preserving aspect ratio
      const naturalAspect = sigImg.naturalWidth / sigImg.naturalHeight;
      const initialWidth = 150;
      el.style.width = initialWidth + 'px';
      el.style.height = (initialWidth / naturalAspect) + 'px';
      el.style.display = 'block';
    };
    
    setStatus('');
    checkReady();
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  }
});

async function loadPageImage() {
  const imgUrl = `/api/pdf/render/${state.pdfId}?page=${state.currentPage}`;
  const img = $('#pdf-img');
  
  return new Promise((resolve, reject) => {
    img.onload = () => {
      // Record dimensions
      state.imgNatural.width = img.naturalWidth;
      state.imgNatural.height = img.naturalHeight;
      resolve();
    };
    img.onerror = reject;
    img.src = imgUrl;
  });
}

function checkReady() {
  if (state.pdfId && state.sigPath) {
    $('#btn-stamp').disabled = false;
  }
}

function setStatus(msg, isError = false) {
  const el = $('#status-message');
  if (!msg) {
    el.style.display = 'none';
    return;
  }
  el.style.display = 'flex';
  el.textContent = msg;
  el.style.color = isError ? '#e53e3e' : 'var(--primary)';
}

// ── Drag & Resize Logic ───────────────────────────────────────────────────

const sigEl = $('#signature-element');
const handle = $('#resize-handle');
const container = $('#pdf-container');

let isDragging = false;
let isResizing = false;
let startX, startY, startRect;

sigEl.addEventListener('mousedown', (e) => {
  if (e.target === handle) return;
  isDragging = true;
  startX = e.clientX;
  startY = e.clientY;
  startRect = sigEl.getBoundingClientRect();
  
  // Prevent drag default (HTML5 drag)
  e.preventDefault();
});

handle.addEventListener('mousedown', (e) => {
  isResizing = true;
  startX = e.clientX;
  startY = e.clientY;
  startRect = sigEl.getBoundingClientRect();
  e.preventDefault();
  e.stopPropagation();
});

document.addEventListener('mousemove', (e) => {
  if (isDragging) {
    const containerRect = container.getBoundingClientRect();
    
    // Calculate new position
    let newX = parseFloat(sigEl.style.left || 50) + (e.clientX - startX);
    let newY = parseFloat(sigEl.style.top || 50) + (e.clientY - startY);
    
    // Constrain to container bounding box
    newX = Math.max(0, Math.min(newX, containerRect.width - sigEl.offsetWidth));
    newY = Math.max(0, Math.min(newY, containerRect.height - sigEl.offsetHeight));
    
    sigEl.style.left = newX + 'px';
    sigEl.style.top = newY + 'px';
    
    startX = e.clientX;
    startY = e.clientY;
  }
  else if (isResizing) {
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    
    // Maintain aspect ratio logic
    const img = $('#sig-img');
    const aspect = img.naturalWidth / img.naturalHeight || 1;
    
    let newWidth = startRect.width + dx;
    if (newWidth < 30) newWidth = 30; // Min size
    
    let newHeight = newWidth / aspect;
    
    sigEl.style.width = newWidth + 'px';
    sigEl.style.height = newHeight + 'px';
  }
});

document.addEventListener('mouseup', () => {
  isDragging = false;
  isResizing = false;
});

// ── Submit Logic ──────────────────────────────────────────────────────────

$('#btn-stamp').addEventListener('click', async () => {
  if (!state.pdfId || !state.sigPath) return;
  
  const containerRect = container.getBoundingClientRect();
  const sigRect = sigEl.getBoundingClientRect();
  
  // X and Y relative to the container DOM element
  const xCss = sigRect.left - containerRect.left;
  const yCss = sigRect.top - containerRect.top;
  const wCss = sigRect.width;
  const hCss = sigRect.height;
  
  // The original PyMuPDF rendering was at 2x Matrix scale AND we might be scaling it via CSS
  // PyMuPDF standard points are 1/72 scale, which equals naturalWidth / 2
  const standardPointsWidth = state.imgNatural.width / 2;
  const scaleRatio = standardPointsWidth / containerRect.width;
  
  const payload = {
    pdf_id: state.pdfId,
    page: state.currentPage,
    signature_path: state.sigPath,
    original_filename: state.originalFilename,
    x: xCss * scaleRatio,
    y: yCss * scaleRatio,
    width: wCss * scaleRatio,
    height: hCss * scaleRatio
  };
  
  $('#btn-stamp').disabled = true;
  $('#btn-stamp').textContent = 'Stamping...';
  
  try {
    const res = await fetch('/api/pdf/stamp_signature', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    
    const data = await res.json();
    if (!data.success) throw new Error(data.error);
    
    $('#download-link').href = data.download_url;
    $('#download-link').download = data.filename;
    $('#download-link').style.display = 'block';
    
    setStatus('Signature applied successfully!');
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  } finally {
    $('#btn-stamp').disabled = false;
    $('#btn-stamp').textContent = 'Apply Signature';
  }
});
})();
