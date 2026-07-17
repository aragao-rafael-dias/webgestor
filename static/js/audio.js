// ==========================================
// AUDIO
// ==========================================

let audioCtx = null;

function obterAudioContext() {
    const AudioContextClass =
        window.AudioContext ??
        window.webkitAudioContext;

    if (!AudioContextClass) {
        return null;
    }

    if (!audioCtx) {
        audioCtx = new AudioContextClass();
    }

    return audioCtx;
}

export async function tocarBip(tipo) {
    try {
        const ctx = obterAudioContext();

        if (!ctx) {
            return;
        }

        if (ctx.state === "suspended") {
            await ctx.resume();
        }

        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        const agora = ctx.currentTime;

        osc.connect(gain);
        gain.connect(ctx.destination);
        gain.gain.setValueAtTime(0.1, agora);

        if (tipo === "nova") {
            osc.type = "sine";
            osc.frequency.setValueAtTime(880, agora);
            gain.gain.exponentialRampToValueAtTime(
                0.00001,
                agora + 0.3
            );
            osc.start(agora);
            osc.stop(agora + 0.3);
            return;
        }

        if (tipo === "resposta") {
            osc.type = "triangle";
            osc.frequency.setValueAtTime(523.25, agora);
            osc.frequency.linearRampToValueAtTime(
                659.25,
                agora + 0.1
            );
            gain.gain.exponentialRampToValueAtTime(
                0.00001,
                agora + 0.4
            );
            osc.start(agora);
            osc.stop(agora + 0.4);
        }
    } catch (error) {
        console.warn("Não foi possível reproduzir o áudio:", error);
    }
}
