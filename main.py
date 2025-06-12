import asyncio
from typing import List

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


@app.get("/shifts")
def read_root():
    url = "http://localhost:8181/shifts"
    try:
        response = httpx.get(url)
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as exc:
        return {"error": f"An error occurred while requesting {url}: {exc}"}
    except httpx.HTTPStatusError as exc:
        return {"error": f"HTTP error occurred: {exc.response.status_code} - {exc.response.text}"}


class ClientShiftVm(BaseModel):
    companyId: str
    userId: str
    startTime: str
    endTime: str
    action: str


class ClientShiftsVm(BaseModel):
    shifts: List[ClientShiftVm]


async def modify_shift(shift: ClientShiftVm):
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8181") as client:
        while True:
            response = await client.post(
                "/shift",
                json=shift.dict()
            )
            if response.status_code == 200:
                return response
            await asyncio.sleep(0.1)


# Here I decided to implement a version that I think would be more suitable for the real environment
async def modify_shift_not_reliable(shift: ClientShiftVm):
    i = 0
    response = None
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8181") as client:
        while i < 5:
            i+= 1
            response = await client.post(
                "/shift",
                json=shift.dict()
            )
            if response.status_code == 200:
                return response
            await asyncio.sleep(0.2 * i)
        return response


@app.post("/clientshifts")
async def modify_shifts(shifts_vm: ClientShiftsVm):
    print(shifts_vm)
    tasks = [modify_shift(shift) for shift in shifts_vm.shifts]
    responses = await asyncio.gather(*tasks)

    success_count = sum(1 for r in responses if r.status_code == 200)
    return {"ok": True, "successful_posts": success_count}


@app.post("/clientshiftsprod")
async def modify_shifts_prod(shifts_vm: ClientShiftsVm):
    print(shifts_vm)
    tasks = [modify_shift_not_reliable(shift) for shift in shifts_vm.shifts]
    responses = await asyncio.gather(*tasks)

    success_count = sum(1 for r in responses if r.status_code == 200)
    return {"ok": True, "successful_posts": success_count}
