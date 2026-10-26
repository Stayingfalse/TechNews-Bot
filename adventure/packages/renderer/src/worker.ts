// A render worker: draws the frames it's asked for and hands back raw RGBA.
import { parentPort, workerData } from "node:worker_threads";
import { OUT_H, OUT_W, type Job, prepare } from "./canvas.ts";

const { job, fps } = workerData as { job: Job; fps: number };
const r = await prepare(job);

parentPort!.on("message", (i: number) => {
  r.draw(i / fps);
  const px = r.ctx.getImageData(0, 0, OUT_W, OUT_H).data;
  const buf = px.buffer.slice(px.byteOffset, px.byteOffset + px.byteLength);
  parentPort!.postMessage({ i, buf }, [buf as ArrayBuffer]);
});
parentPort!.postMessage({ ready: true });
