from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class RegistrationState(StatesGroup):
    waiting_for_contact = State()
    waiting_for_full_name = State()


class ReceiptState(StatesGroup):
    waiting_for_photo = State()


class ProfileState(StatesGroup):
    waiting_for_new_name = State()


class AdminAddShopState(StatesGroup):
    waiting_for_name = State()
    waiting_for_address = State()
    waiting_for_samples = State()


class AdminSetDatesState(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()


class AdminSetMinAmountState(StatesGroup):
    waiting_for_amount = State()


class AdminSetTimeRangeState(StatesGroup):
    waiting_for_start = State()
    waiting_for_end = State()


class AdminSearchState(StatesGroup):
    waiting_for_query = State()


class AdminStartCampaignStates(StatesGroup):
    start_date = State()
    end_date = State()
    start_time = State()
    end_time = State()
    shops = State()
    min_amount = State()


class AdminStatsByPeriodStates(StatesGroup):
    start_date = State()
    end_date = State()


class AdminWinnerState(StatesGroup):
    waiting_for_count = State()


class AdminSetChannelState(StatesGroup):
    waiting_for_channel = State()
