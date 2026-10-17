// Assign video sources only when playback is needed. Posters remain immediately visible.
window.loadVideoSource = function (video) {
  if (video.dataset.src) {
    video.src = video.dataset.src;
    delete video.dataset.src;
    video.load();
  }
};
const userPaused = new WeakSet();
const manualPlay = new WeakSet();
const videoButtons = document.querySelectorAll('[data-video]');
function syncButton(video) {
  const button = document.querySelector(`[data-video="${video.id}"]`);
  if (!button) return;
  button.setAttribute('aria-label', `${video.paused ? 'Play' : 'Pause'} ${button.dataset.videoLabel || 'skill demonstration'}`);
  button.querySelector('use').setAttribute('href', video.paused ? '#play' : '#pause');
}
videoButtons.forEach(button => {
  const video = document.getElementById(button.dataset.video);
  button.addEventListener('click', () => {
    if (video.paused) {
      userPaused.delete(video);
      manualPlay.add(video);
      window.loadVideoSource(video);
      video.play().catch(() => button.setAttribute('aria-label', 'Retry playing demonstration'));
    } else {
      userPaused.add(video);
      video.pause();
    }
  });
  video.addEventListener('play', () => syncButton(video));
  video.addEventListener('pause', () => syncButton(video));
  syncButton(video);
});
document.getElementById('contact-form').addEventListener('submit', event => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const body = `Hi Daidai Labs,\n\nI'm interested in ${form.get('interest')}.\n\nTask: ${form.get('task')}\n\nName: ${form.get('name')}\nEmail: ${form.get('email')}`;
  location.href = `mailto:contact@daidailabs.com?subject=${encodeURIComponent('Let’s talk — ' + form.get('interest'))}&body=${encodeURIComponent(body)}`;
  document.getElementById('form-status').textContent = 'Your email draft is ready. Send it in your email app. If nothing opened, write to contact@daidailabs.com.';
});
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
const videos = [...document.querySelectorAll('video:not([data-skill-scene])')];
const visibleVideos = new Set();
function updatePlayback(video) {
  const shouldPlay = !video.closest('.layer-row')?.hidden && visibleVideos.has(video) && !document.hidden && !userPaused.has(video) && (!motionPreference.matches || manualPlay.has(video));
  if (shouldPlay) {
    window.loadVideoSource(video);
    video.play().catch(() => {});
  } else video.pause();
}
videos.forEach(video => { video.loop = true; video.muted = true; });
const observer = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting && entry.intersectionRatio >= .1) visibleVideos.add(entry.target);
    else visibleVideos.delete(entry.target);
    updatePlayback(entry.target);
  });
}, {threshold: [0, .1]});
videos.forEach(video => observer.observe(video));
document.addEventListener('visibilitychange', () => videos.forEach(updatePlayback));
motionPreference.addEventListener('change', () => videos.forEach(updatePlayback));

document.addEventListener('layerchange', () => videos.forEach(updatePlayback));
