import asyncio
import uuid
from typing import List

import httpx
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import (
    ShiftsRequest, get_db, Shift, get_shard_id, shard_sessions,
    NUM_SHARDS,
    init_db
)

app = FastAPI()


@app.get("/shifts")
def read_root():
    return {"message": "Shifts endpoint is working!", "shards": NUM_SHARDS}


@app.on_event("startup")
def startup():
    init_db()


class ClientShiftVm(BaseModel):
    companyId: str
    userId: str
    startTime: str
    endTime: str
    action: str


class ClientShiftsVm(BaseModel):
    shifts: List[ClientShiftVm]


async def modify_shift(shift: ClientShiftVm, request_id: str):
    shard_id = get_shard_id(shift.companyId)
    db = shard_sessions[shard_id]()

    try:
        shift_record = Shift(
            shift_id=str(uuid.uuid4()),
            request_id=request_id,
            company_id=shift.companyId,
            user_id=shift.userId,
            start_time=shift.startTime,
            end_time=shift.endTime,
            action=shift.action,
            status="pending"
        )
        db.add(shift_record)
        db.commit()

        try:
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8181") as client:
                while True:
                    response = await client.post(
                        "/shift",
                        json=shift.dict()
                    )
                    if response.status_code == 200:
                        shift_record.status = "success"
                        db.commit()
                        return response
                    await asyncio.sleep(3)
        except Exception as e:
            shift_record.status = "failed"
            db.commit()
            raise e
    finally:
        db.close()


async def process_shifts_background(tasks, request_id):
    await asyncio.gather(*tasks)

    request_db = shard_sessions[0]()

    try:
        request = request_db.query(ShiftsRequest).filter(ShiftsRequest.id == request_id).first()

        total_success = 0
        total_shifts = 0

        for shard_id in range(NUM_SHARDS):
            shard_db = shard_sessions[shard_id]()
            try:
                successful_count = shard_db.query(Shift).filter(
                    Shift.request_id == request_id,
                    Shift.status == "success"
                ).count()
                all_count = shard_db.query(Shift).filter(
                    Shift.request_id == request_id
                ).count()
                total_success += successful_count
                total_shifts += all_count
            finally:
                shard_db.close()

        if request:
            request.status = "success" if total_success == total_shifts else "failed"
            request_db.commit()
    finally:
        request_db.close()


@app.post("/clientshifts")
async def modify_shifts(shifts_vm: ClientShiftsVm, db: Session = Depends(get_db)):
    request_id = str(uuid.uuid4())

    # Only create the request in shard 0
    shard_db = shard_sessions[0]()
    try:
        new_request = ShiftsRequest(
            id=request_id,
            status="pending"
        )
        shard_db.add(new_request)
        shard_db.commit()
    finally:
        shard_db.close()

    tasks = [modify_shift(shift, request_id) for shift in shifts_vm.shifts]
    asyncio.create_task(process_shifts_background(tasks, request_id))

    return {
        "request_id": request_id,
        "status": "pending",
        "successful_posts": 0
    }


@app.get("/status/{request_id}")
def get_request_status(request_id: str, db: Session = Depends(get_db)):
    request = db.query(ShiftsRequest).filter(ShiftsRequest.id == request_id).first()

    if not request:
        return {"error": "Request not found"}, 404

    successful_count = 0
    for shard_id in range(NUM_SHARDS):
        shard_db = shard_sessions[shard_id]()
        try:
            successful_count += shard_db.query(Shift).filter(
                Shift.request_id == request_id,
                Shift.status == "success"
            ).count()
        finally:
            shard_db.close()

    return {
        "request_id": request.id,
        "status": request.status,
        "successful_posts": successful_count
    }
