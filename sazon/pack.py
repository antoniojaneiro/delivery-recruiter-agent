"""Grupo Sazón's fixed wording, Spanish and English (D63)."""
from screener.model import Language, Outcome
from screener.pack import Pack, SlotTexts, Text


def bi(es: str, en: str) -> Text:
    return {Language.ES: es, Language.EN: en}


SLOTS = SlotTexts(
    offer={
        "first": bi("¡Genial, tu perfil encaja! Elige una hora para una llamada corta con el equipo:",
                    "Great, your profile fits! Pick a time for a short call with the team:"),
        "taken": bi("Ese horario ya no está libre. Estas son las opciones disponibles:",
                    "That time is no longer free. These are the options available:"),
        "unclear": bi("No me quedó claro. Elige una opción:", "I didn't quite get that. Pick an option:"),
        "reminder": bi("Te recuerdo las horas disponibles para tu llamada:",
                       "A reminder of the times available for your call:"),
    },
    offer_end=bi(
        "Responde con el número. Si ninguna te viene bien, responde 'ninguna' y un reclutador te escribirá en un máximo de 48 horas.",
        "Reply with the number. If none suits you, reply 'none' and a recruiter will message you within 48 hours."),
    booked=bi("Listo, queda reservada tu llamada: {label}. Un reclutador te llamará a esa hora.",
              "Done, your call is booked: {label}. A recruiter will call you then."),
    already_booked=bi("Tu llamada ya está reservada: {label}. Si hay algún cambio, un reclutador te escribirá.",
                      "Your call is already booked: {label}. If anything changes, a recruiter will message you."),
    cancelled=bi("La llamada que tenías reservada ya no está disponible. Un reclutador te escribirá para darte otra hora.",
                 "The call you had booked is no longer available. A recruiter will write to you with another time."),
)

PACK = Pack(
    company="Grupo Sazón",
    default_language=Language.ES,
    consent=bi(
        "Hola, soy el asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud "
        "de repartidor. Tus respuestas se procesan con un servicio de IA externo y siempre las revisa un "
        "reclutador. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?",
        "Hi, I'm Grupo Sazón's virtual assistant (an AI). I'll ask a few questions for your delivery "
        "driver application. Your answers are processed by an external AI service and always reviewed by a "
        "recruiter. Is it OK if I save your answers for the recruiting team?"),
    closed=bi("Por ahora no estamos aceptando solicitudes. ¡Gracias por tu interés!",
              "We are not accepting applications right now. Thank you for your interest!"),
    error=bi("Tuve un problema técnico. ¿Puedes repetir tu último mensaje?",
             "I had a technical problem. Could you repeat your last message?"),
    reminder=bi("Hola, ¿sigues interesado en la solicitud? Cuando quieras, seguimos donde lo dejamos.",
                "Hi, are you still interested in the application? We can pick up where we left off."),
    unclear=bi("No me quedó claro y necesito este dato para continuar. ",
               "That wasn't clear, and I need this to move forward. "),
    confirm_area=bi("¿Te refieres a {suggestion}?", "Do you mean {suggestion}?"),
    confirm_change=bi("Antes me dijiste {old}. ¿Lo cambio a {new}?",
                      "Earlier you told me {old}. Shall I change it to {new}?"),
    blocked=bi("No puedo continuar con tu solicitud hasta que me indiques {what}.",
               "I can't continue with your application until you tell me {what}."),
    close={
        Outcome.QUALIFIED: bi(
            "¡Genial, tu perfil encaja! Un reclutador te escribirá en un máximo de 48 horas para el siguiente paso.",
            "Great, your profile fits! A recruiter will message you within 48 hours with the next step."),
        Outcome.ENDED_OFF_TOPIC: bi(
            "Has enviado varios mensajes ajenos a la solicitud y en Grupo Sazón pedimos un trato profesional, "
            "así que termino la conversación. Un reclutador puede revisarlo.",
            "You have sent several messages unrelated to the application, and Grupo Sazón asks for a professional "
            "tone, so I'm ending the conversation. A recruiter can review it."),
        Outcome.WITHDRAWN: bi(
            "Entendido, paramos aquí. Si quieres retomar tu solicitud, escribe «continuar». Gracias por tu tiempo.",
            "Understood, we'll stop here. If you want to pick your application back up, write «continue». "
            "Thanks for your time."),
    },
    close_other=bi("Gracias por tu tiempo. Cuando quieras retomar tu solicitud, escríbenos.",
                   "Thanks for your time. Write to us whenever you want to pick up your application."),
    close_no_consent=bi(
        "Sin tu permiso para guardar las respuestas no puedo continuar. Si cambias de opinión, escribe «sí» y empezamos.",
        "Without your permission to save your answers I can't continue. If you change your mind, write «yes» and we'll start."),
    close_repeat={
        Outcome.QUALIFIED: bi(
            "Ya tenemos todo lo que necesitamos: un reclutador te escribirá en un máximo de 48 horas.",
            "We already have everything we need: a recruiter will message you within 48 hours."),
    },
    close_repeat_withdrawn=bi("Has dejado la solicitud. Si quieres retomarla, escribe «continuar».",
                              "You have left the application. If you want to pick it up, write «continue»."),
    close_repeat_other=bi("Esta conversación ya está cerrada. Un reclutador revisará tu caso.",
                          "This conversation is closed. A recruiter will review your case."),
    notices={
        "human": bi("Soy un asistente virtual: un reclutador revisará tu solicitud y podrá hablar contigo después.",
                    "I'm a virtual assistant: a recruiter will review your application and can talk to you afterwards."),
        "pay": bi("Sobre el sueldo, te informará un reclutador.", "A recruiter will tell you about the pay."),
        "changed": bi("Hecho, lo he cambiado.", "Done, I've changed it."),
        "kept": bi("De acuerdo, lo dejo como estaba.", "OK, I'll leave it as it was."),
        "offtopic": bi("Eso no forma parte de mi función; sigamos con tu solicitud.",
                       "That's not part of my role; let's continue with your application."),
    },
    slots=SLOTS,
)
