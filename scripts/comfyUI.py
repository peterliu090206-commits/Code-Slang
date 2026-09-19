#!/usr/bin/env python3
"""Text-to-image / image-to-image client for a local ComfyUI server.

Builds an SDXL checkpoint workflow dictionary and queues it via the
ComfyUI HTTP API (stdlib only — no third-party dependencies).

Usage:
    py -3.12 scripts/comfyUI.py --positive "..." --prefix rizz --output docs/data/images/rizz.png
    py -3.12 scripts/comfyUI.py --positive "..." --init-image docs/data/memes/rizz.jpg --denoise 0.65 --prefix rizz --output docs/data/images/rizz.png
    py -3.12 scripts/comfyUI.py --positive "..." --print-workflow
    py -3.12 scripts/comfyUI.py --positive "..." --background
"""

import argparse
import json
import mimetypes
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

DEFAULT_SERVER = "http://127.0.0.1:8188"
DEFAULT_CKPT = "dreamshaper_xl_alpha2.safetensors"
DEFAULT_NEGATIVE = (
    "blurry, low quality, distorted face, extra fingers, watermark, text, logo, deformed, "
    "nsfw, nude, nudity, naked, sexually explicit, pornographic, erotic content, "
    "excessive skin exposure, gore, blood, graphic violence, disturbing imagery, hate symbols"
)


def build_txt2img_workflow(
    positive,
    negative=DEFAULT_NEGATIVE,
    width=1024,
    height=1024,
    filename_prefix="comfy",
    ckpt_name=DEFAULT_CKPT,
    seed=None,
    steps=25,
    cfg=7.0,
    sampler_name="euler",
    scheduler="normal",
    batch_size=1,
):
    """Build a 7-node SDXL CheckpointLoaderSimple txt2img workflow dict.

    Nodes: 1 CheckpointLoaderSimple, 2 CLIPTextEncode (+), 3 CLIPTextEncode (-),
    4 EmptyLatentImage, 5 KSampler, 6 VAEDecode, 7 SaveImage.
    """
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": width, "height": height, "batch_size": batch_size},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": filename_prefix}},
    }


def build_img2img_workflow(
    positive,
    init_image,
    negative=DEFAULT_NEGATIVE,
    denoise=0.65,
    filename_prefix="comfy",
    ckpt_name=DEFAULT_CKPT,
    seed=None,
    steps=25,
    cfg=7.0,
    sampler_name="euler",
    scheduler="normal",
):
    """Build an SDXL img2img workflow dict seeded by an uploaded input image.

    Nodes: 1 CheckpointLoaderSimple, 2 CLIPTextEncode (+), 3 CLIPTextEncode (-),
    8 LoadImage, 9 VAEEncode, 5 KSampler, 6 VAEDecode, 7 SaveImage.

    init_image must already exist in the ComfyUI input dir — see upload_image().
    denoise controls the transform strength: ~0.2-0.4 subtle touch-up that keeps
    the starter composition, 0.6-0.8 strong restyle that changes much more on
    top of the initial picture while keeping general layout, 1.0 ignores the
    input entirely. Default 0.65 = strong cartoony restyle.
    Output size is driven by the input image via VAEEncode (no EmptyLatentImage).
    """
    if seed is None:
        seed = random.randint(1, 2**31 - 1)
    if not init_image:
        raise ValueError("init_image filename is required for img2img")
    denoise = float(denoise)
    if not 0.0 < denoise <= 1.0:
        raise ValueError("denoise must be in (0.0, 1.0]")
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "8": {"class_type": "LoadImage", "inputs": {"image": init_image}},
        "9": {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["1", 2]}},
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["9", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
                "sampler_name": sampler_name,
                "scheduler": scheduler,
                "denoise": denoise,
            },
        },
        "6": {"class_type": "VAEDecode", "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": ["6", 0], "filename_prefix": filename_prefix}},
    }


def _encode_multipart(fields, file_field, filename, file_bytes, file_type):
    """Encode multipart/form-data body. Returns (body_bytes, content_type)."""
    boundary = uuid.uuid4().hex
    buf = bytearray()
    for key, value in fields.items():
        buf += f"--{boundary}\r\n".encode()
        buf += f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
        buf += f"{value}\r\n".encode()
    buf += f"--{boundary}\r\n".encode()
    buf += (
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
        f"Content-Type: {file_type}\r\n\r\n"
    ).encode()
    buf += file_bytes
    buf += f"\r\n--{boundary}--\r\n".encode()
    return bytes(buf), f"multipart/form-data; boundary={boundary}"


def upload_image(image_path, server, timeout=60, overwrite=True):
    """Upload a local image into the ComfyUI input dir. Returns server filename.

    POSTs multipart/form-data to {server}/upload/image so a later LoadImage
    node can reference it by name.
    """
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"init image not found: {path}")
    file_bytes = path.read_bytes()
    if len(file_bytes) == 0:
        raise ValueError(f"init image is empty: {path}")
    if len(file_bytes) > 50 * 1024 * 1024:
        raise ValueError(f"init image exceeds 50MB ComfyUI limit: {path}")
    file_type = mimetypes.guess_type(path.name)[0] or "image/png"
    if not file_type.startswith("image/"):
        file_type = "image/png"
    fields = {"overwrite": "true" if overwrite else "false", "type": "input"}
    body, content_type = _encode_multipart(fields, "image", path.name, file_bytes, file_type)
    req = urllib.request.Request(
        f"{server}/upload/image", data=body, headers={"Content-Type": content_type}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            result = json.load(r)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500] if hasattr(exc, "read") else ""
        raise RuntimeError(f"ComfyUI upload failed HTTP {exc.code}: {detail}")
    name = (result.get("name") or "").strip()
    if not name:
        raise RuntimeError(f"ComfyUI upload returned no filename: {result}")
    subfolder = (result.get("subfolder") or "").strip().strip("/")
    if subfolder:
        return f"{subfolder}/{name}"
    return name


def queue_prompt(workflow, server):
    data = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(
        f"{server}/prompt", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def wait_completed(prompt_id, server, timeout, poll_interval=5):
    deadline = time.time() + timeout
    while True:
        with urllib.request.urlopen(f"{server}/history/{prompt_id}", timeout=30) as r:
            history = json.load(r)
        entry = history.get(prompt_id)
        if entry and entry.get("status", {}).get("completed"):
            return entry
        if time.time() >= deadline:
            raise TimeoutError(f"timed out after {timeout}s waiting for {prompt_id}")
        time.sleep(poll_interval)


def download_first_image(entry, server, dest):
    outputs = entry.get("outputs", {})
    for node_id in sorted(outputs, key=int):
        for img in outputs[node_id].get("images", []):
            qs = urllib.parse.urlencode(
                {
                    "filename": img["filename"],
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                }
            )
            dest.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(f"{server}/view?{qs}", str(dest))
            return img
    raise RuntimeError("no images found in completed outputs")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Queue a ComfyUI SDXL txt2img/img2img workflow.")
    p.add_argument("--positive", required=True, help="Positive prompt text.")
    p.add_argument("--negative", default=DEFAULT_NEGATIVE, help="Negative prompt text.")
    p.add_argument("--width", type=int, default=1024, help="txt2img latent width (ignored with --init-image).")
    p.add_argument("--height", type=int, default=1024, help="txt2img latent height (ignored with --init-image).")
    p.add_argument("--init-image", default=None, help="Local meme/starter image to upload and restyle via img2img.")
    p.add_argument("--denoise", type=float, default=0.65, help="img2img transform strength in (0, 1] (default 0.65 strong restyle).")
    p.add_argument("--ckpt", default=DEFAULT_CKPT, help="Checkpoint file (default: dreamshaper_xl_alpha2 cartoony/artistic).")
    p.add_argument("--prefix", default="comfy", help="SaveImage filename_prefix.")
    p.add_argument("--output", default=None, help="Where to save the PNG (default: docs/data/images/<prefix>.png).")
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--seed", type=int, default=None, help="Random if omitted.")
    p.add_argument("--steps", type=int, default=25)
    p.add_argument("--cfg", type=float, default=7.0)
    p.add_argument("--sampler", default="euler")
    p.add_argument("--scheduler", default="normal")
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--timeout", type=int, default=600)
    p.add_argument("--background", action="store_true", help="Queue and exit without waiting.")
    p.add_argument("--print-workflow", action="store_true", help="Print workflow JSON and exit.")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.init_image:
        if args.print_workflow:
            workflow = build_img2img_workflow(
                positive=args.positive,
                init_image=Path(args.init_image).name,
                negative=args.negative,
                denoise=args.denoise,
                filename_prefix=args.prefix,
                ckpt_name=args.ckpt,
                seed=args.seed,
                steps=args.steps,
                cfg=args.cfg,
                sampler_name=args.sampler,
                scheduler=args.scheduler,
            )
            print(json.dumps(workflow, indent=2))
            return 0
        server_name = upload_image(args.init_image, args.server)
        print(f"uploaded {args.init_image} -> {server_name}")
        workflow = build_img2img_workflow(
            positive=args.positive,
            init_image=server_name,
            negative=args.negative,
            denoise=args.denoise,
            filename_prefix=args.prefix,
            ckpt_name=args.ckpt,
            seed=args.seed,
            steps=args.steps,
            cfg=args.cfg,
            sampler_name=args.sampler,
            scheduler=args.scheduler,
        )
    else:
        workflow = build_txt2img_workflow(
            positive=args.positive,
            negative=args.negative,
            width=args.width,
            height=args.height,
            filename_prefix=args.prefix,
            ckpt_name=args.ckpt,
            seed=args.seed,
            steps=args.steps,
            cfg=args.cfg,
            sampler_name=args.sampler,
            scheduler=args.scheduler,
            batch_size=args.batch,
        )
    seed = workflow["5"]["inputs"]["seed"]
    if args.print_workflow:
        print(json.dumps(workflow, indent=2))
        return 0
    res = queue_prompt(workflow, args.server)
    prompt_id = res["prompt_id"]
    print(f"queued prompt_id={prompt_id} seed={seed}")
    if args.background:
        return 0
    entry = wait_completed(prompt_id, args.server, args.timeout)
    dest = Path(args.output) if args.output else Path("docs/data/images") / f"{args.prefix}.png"
    img = download_first_image(entry, args.server, dest)
    print(f"saved {dest} ({dest.stat().st_size} bytes) from {img['filename']} seed={seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
