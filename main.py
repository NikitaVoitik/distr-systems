import asyncio
import uuid
from typing import List

import httpx
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import ShiftsRequest, get_db, Shift, SessionLocal

app = FastAPI()


@app.get("/shifts")
def read_root():
    return {"message": "Shifts endpoint is working!"}


class ClientShiftVm(BaseModel):
    companyId: str
    userId: str
    startTime: str
    endTime: str
    action: str


class ClientShiftsVm(BaseModel):
    shifts: List[ClientShiftVm]


async def modify_shift(shift: ClientShiftVm, request_id: str, db: Session):
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
                await asyncio.sleep(1)
    except Exception as e:
        shift_record.status = "failed"
        db.commit()
        raise e


async def process_shifts_background(tasks, request_id, db):
    await asyncio.gather(*tasks)

    request = db.query(ShiftsRequest).filter(ShiftsRequest.id == request_id).first()
    successful_count = db.query(Shift).filter(Shift.request_id == request_id, Shift.status == "success").count()
    all_count = db.query(Shift).filter(Shift.request_id == request_id).count()
    if request:
        request.status = "success" if successful_count == all_count else "failed"
        db.commit()


@app.post("/clientshifts")
async def modify_shifts(shifts_vm: ClientShiftsVm, db: Session = Depends(get_db)):
    request_id = str(uuid.uuid4())

    new_request = ShiftsRequest(
        id=request_id,
        status="pending"
    )
    db.add(new_request)
    db.commit()


    tasks = [modify_shift(shift, request_id, SessionLocal()) for shift in shifts_vm.shifts]
    asyncio.create_task(process_shifts_background(tasks, request_id, SessionLocal()))

    return {
        "request_id": request_id,
        "status": "pending",
        "successful_posts": 0
    }

@app.get("/status/{request_id}")
def get_request_status(request_id: str, db: Session = Depends(get_db)):
    request = db.query(ShiftsRequest).filter(ShiftsRequest.id == request_id).first()
    successful_count = db.query(Shift).filter(Shift.request_id == request_id, Shift.status == "success").count()
    if request:
        return {"request_id": request.id, "status": request.status, "successful_posts": successful_count}
    return {"error": "Request not found"}, 404