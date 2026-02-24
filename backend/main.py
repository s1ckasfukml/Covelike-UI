#!/usr/bin/env python3
"""FastAPI backend for Seed-VC Pipeline UI - subprocess wrapper"""
import sys
import os
import asyncio
import uuid
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import aiofiles

app = FastAPI(title="Seed-VC Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path("D:/Covelike-UI/uploads")
OUTPUT_DIR = Path("D:/Covelike-UI/outputs")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PIPELINE_DIR = Path("C:/seedvc-pipeline")
PIPELINE_PYTHON = PIPELINE_DIR / "venv" / "Scripts" / "python.exe"
PIPELINE_SCRIPT = PIPELINE_DIR / "pipeline_cli.py"

jobs: Dict[str, Dict[str, Any]] = {}


class PipelineParams(BaseModel):
    engine: str = "seedvc"
    steps: int = 30
    cfg_rate: float = 0.0
    pitch_shift: int = 0
    f0_condition: bool = True
    auto_f0_adjust: bool = False
    amphion_fm_steps: int = 32
    amphion_use_shifted: bool = True
    amphion_shift_content_style: bool = False
    amphion_whisper_perturb: bool = False
    amphion_cfg: float = 1.0
    amphion_rescale_cfg: float = 0.75
    use_pitch_tuner: bool = True
    use_distillation: bool = True
    use_resemble_enhance: bool = False
    resemble_nfe: int = 32
    use_chorus_extract: bool = False
    skip_waveform_align: bool = False
    inst_gain_db: float = 0.0
    backs_gain_db: float = -3.0
    lead_gain_db: float = 0.0


@app.get("/")
async def root():
    return {"status": "ok", "message": "Seed-VC Pipeline API"}


@app.get("/health")
async def health():
    import torch
    return {
        "status": "ok",
        "cuda": torch.cuda.is_available(),
        "device": "cuda" if torch.cuda.is_available() else "cpu",
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    }


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())[:8]
    ext = Path(file.filename).suffix or ".wav"
    file_path = UPLOAD_DIR / f"{file_id}{ext}"
    
    async with aiofiles.open(file_path, 'wb') as f:
        content = await file.read()
        await f.write(content)
    
    return {"file_id": file_id, "filename": file.filename, "path": str(file_path)}


@app.post("/process")
async def process_audio(
    background_tasks: BackgroundTasks,
    track_id: str = Form(...),
    reference_id: str = Form(...),
    params: str = Form("{}")
):
    job_id = str(uuid.uuid4())[:8]
    
    track_files = list(UPLOAD_DIR.glob(f"{track_id}.*"))
    ref_files = list(UPLOAD_DIR.glob(f"{reference_id}.*"))
    
    if not track_files:
        raise HTTPException(404, f"Track not found: {track_id}")
    if not ref_files:
        raise HTTPException(404, f"Reference not found: {reference_id}")
    
    track_path = str(track_files[0])
    ref_path = str(ref_files[0])
    
    try:
        p = PipelineParams(**json.loads(params))
    except Exception as e:
        raise HTTPException(400, f"Invalid params: {e}")
    
    jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "progress": 0,
        "created_at": datetime.now().isoformat(),
        "track": track_path,
        "reference": ref_path,
        "params": p.dict(),
        "result": None,
        "error": None
    }
    
    background_tasks.add_task(run_pipeline_subprocess, job_id, track_path, ref_path, p)
    
    return {"job_id": job_id, "status": "started"}


def run_pipeline_subprocess(job_id: str, track_path: str, ref_path: str, params: PipelineParams):
    """Run pipeline via subprocess"""
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["progress"] = 10
        
        # Build command
        cmd = [
            str(PIPELINE_PYTHON),
            str(PIPELINE_SCRIPT),
            "--mix", track_path,
            "--ref", ref_path,
            "--engine", params.engine,
            "--steps", str(params.steps),
            "--cfg", str(params.cfg_rate),
            "--pitch-shift", str(params.pitch_shift),
            "--f0-condition", str(int(params.f0_condition)),
            "--auto-f0", str(int(params.auto_f0_adjust)),
            "--amphion-fm-steps", str(params.amphion_fm_steps),
            "--amphion-shift-prosody", str(int(params.amphion_use_shifted)),
            "--amphion-shift-content", str(int(params.amphion_shift_content_style)),
            "--amphion-whisper-perturb", str(int(params.amphion_whisper_perturb)),
            "--amphion-cfg", str(params.amphion_cfg),
            "--amphion-rescale-cfg", str(params.amphion_rescale_cfg),
            "--pitch-tuner", str(int(params.use_pitch_tuner)),
            "--distillation", str(int(params.use_distillation)),
            "--resemble", str(int(params.use_resemble_enhance)),
            "--resemble-nfe", str(params.resemble_nfe),
            "--chorus", str(int(params.use_chorus_extract)),
            "--skip-waveform-align", str(int(params.skip_waveform_align)),
            "--inst-gain", str(params.inst_gain_db),
            "--backs-gain", str(params.backs_gain_db),
            "--lead-gain", str(params.lead_gain_db),
            "--output-json",
        ]
        
        result = subprocess.run(
            cmd,
            cwd=str(PIPELINE_DIR),
            capture_output=True,
            text=True,
            timeout=1800
        )
        
        if result.returncode != 0:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = result.stderr[-500:] if result.stderr else "Unknown error"
            return
        
        # Parse JSON output from stdout
        output_lines = result.stdout.strip().split('\n')
        json_line = None
        for line in reversed(output_lines):
            if line.startswith('{') and 'final_mix' in line:
                json_line = line
                break
        
        if json_line:
            output_data = json.loads(json_line)
            jobs[job_id]["result"] = output_data
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
        else:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = "No output JSON found"
        
    except subprocess.TimeoutExpired:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = "Timeout (30 min)"
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)


@app.get("/job/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    return jobs[job_id]


@app.get("/jobs")
async def list_jobs():
    return list(jobs.values())


@app.get("/download/{job_id}")
async def download_result(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "Job not found")
    
    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(400, "Job not completed")
    
    result_path = job["result"].get("final_mix_mp3") or job["result"].get("final_mix")
    if not result_path or not Path(result_path).exists():
        raise HTTPException(404, "Result file not found")
    
    return FileResponse(result_path, media_type="audio/mpeg", filename=Path(result_path).name)


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    if job_id in jobs:
        del jobs[job_id]
    return {"status": "deleted"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
