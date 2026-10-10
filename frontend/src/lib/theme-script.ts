// Shared with the server layout, so it must not live in a "use client" module.
export const PREFS_KEY = "nigraan.prefs";

/** Runs before first paint (inline in <head>) so a dark-mode user never sees a white flash. */
export const THEME_BOOT_SCRIPT = `(function(){try{var p=JSON.parse(localStorage.getItem(${JSON.stringify(PREFS_KEY)})||"{}");var t=p.theme||"system";var r=document.documentElement;if(t==="dark"||(t==="system"&&matchMedia("(prefers-color-scheme: dark)").matches))r.classList.add("dark");if(p.animations===false)r.classList.add("reduce-motion");}catch(e){}})();`;
