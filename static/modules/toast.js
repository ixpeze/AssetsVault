// ── Toast Notification ──

export function showToast(msg, type = "info") {
    const styles = {
        success: "bg-green-600/90 border-green-500/50",
        error: "bg-red-600/90 border-red-500/50",
        warning: "bg-amber-600/90 border-amber-500/50",
        info: "bg-primary/90 border-primary/50",
    };
    const icons = { success: "check_circle", error: "error", warning: "warning", info: "info" };
    const cls = styles[type] || styles.info;
    const icon = icons[type] || icons.info;

    const toast = document.createElement("div");
    toast.className = `fixed bottom-6 left-1/2 -translate-x-1/2 z-[60] flex items-center gap-2 px-4 py-2.5 ${cls} border text-white text-sm font-medium rounded-lg shadow-xl backdrop-blur-sm transition-all duration-300`;
    toast.innerHTML = `<span class="material-symbols-outlined text-[16px]">${icon}</span><span>${msg}</span>`;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateX(-50%) translateY(8px)";
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}
