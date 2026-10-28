"""Grupo Sazón's fixed wording, Spanish and English (D63)."""
from screener.model import Language, Outcome
from screener.pack import CvTexts, Pack, SlotTexts, Text


def bi(es: str, en: str) -> Text:
    return {Language.ES: es, Language.EN: en}


SLOTS = SlotTexts(
    offer={
        "first": bi("¡Genial, tu perfil encaja! Reserva una llamada para hablar con un reclutador:",
                    "Great, your profile fits! Book a call to talk with a recruiter:"),
        "taken": bi("Ese horario ya no está libre. Estas son las opciones disponibles:",
                    "That time is no longer free. These are the options available:"),
        "unclear": bi("No me quedó claro. Elige una opción:", "I didn't quite get that. Pick an option:"),
        "reminder": bi("Te recuerdo las horas disponibles para tu llamada:",
                       "A reminder of the times available for your call:"),
    },
    offer_end=bi(
        "Responde con el número. Si ninguna te viene bien, responde 'ninguna' y podrás reservar más adelante escribiéndonos otra vez.",
        "Reply with the number. If none suits you, reply 'none' and you can book later by writing to us again."),
    booked=bi("Listo, queda reservada tu llamada: {label}. Un reclutador te llamará a esa hora.",
              "Done, your call is booked: {label}. A recruiter will call you then."),
    already_booked=bi("Tu llamada ya está reservada: {label}. Si hay algún cambio, un reclutador te escribirá.",
                      "Your call is already booked: {label}. If anything changes, a recruiter will message you."),
    cancelled=bi("La llamada que tenías reservada ya no está disponible.",
                 "The call you had booked is no longer available."),
    scheduled=bi("Un reclutador ha reservado tu llamada: {label}. Te llamará a esa hora.",
                 "A recruiter has booked your call: {label}. They will call you then."),
    moved=bi("Un reclutador ha cambiado tu llamada: ahora es {label}. Te llamará a esa hora.",
             "A recruiter has changed your call: it is now {label}. They will call you then."),
    later=bi("Tu perfil encaja. Cuando quieras reservar tu llamada, escríbenos y te muestro los horarios libres.",
             "Your profile fits. Whenever you want to book your call, write to us and I'll show you the free times."),
)

CV = CvTexts(
    offer=bi("Si quieres ir más rápido, puedes subir tu CV en PDF (es opcional) y rellenaré lo que pueda.",
             "If you want to go faster, you can upload your CV as a PDF (it's optional) and I'll fill in what I can."),
    notice=bi("Tu CV (solo PDF, máximo 2 MB) lo verá únicamente el equipo de reclutamiento y se procesa con un servicio "
              "de IA externo para adelantar tus respuestas. Puedes pedir que se borre junto con el resto de tus datos.",
              "Your CV (PDF only, 2 MB at most) will only be seen by the recruiting team and is processed by an external "
              "AI service to fill in your answers. You can ask for it to be erased along with the rest of your data."),
    read_back=bi("He leído tu CV y he tomado estos datos: {items}. Si algo no es correcto, dímelo.",
                 "I read your CV and took this: {items}. If anything is wrong, tell me."),
    unreadable=bi("No he podido sacar datos de tu CV, pero el equipo de reclutamiento podrá verlo. Seguimos con las preguntas.",
                  "I couldn't get any answers out of your CV, but the recruiting team will be able to see it. Let's go on with the questions."),
    invalid=bi("Solo puedo aceptar un CV en PDF de hasta 2 MB. Prueba con otro archivo o responde a las preguntas.",
               "I can only accept a CV as a PDF of up to 2 MB. Try another file or answer the questions."),
    not_now=bi("Ya no es el momento de subir el CV. Sigamos con las preguntas.",
               "It's too late to upload a CV now. Let's go on with the questions."),
)

PACK = Pack(
    company="Grupo Sazón",
    default_language=Language.ES,
    consent=bi(
        "Hola, soy Sofía, la asistente virtual (una IA) de Grupo Sazón. Te haré unas preguntas para tu solicitud "
        "de repartidor. Tus respuestas se procesan con un servicio de IA externo y siempre las revisa un "
        "reclutador. ¿Te parece bien que guarde tus respuestas para el equipo de reclutamiento?",
        "Hi, I'm Sofía, Grupo Sazón's virtual assistant (an AI). I'll ask a few questions for your delivery "
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
            "¡Genial, tu perfil encaja! Ahora mismo no hay horarios libres para tu llamada: escríbenos más tarde y podrás reservarla.",
            "Great, your profile fits! There are no free times for your call right now: write to us later and you can book it."),
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
            "Tu perfil ya encaja. Ahora mismo no hay horarios libres: escríbenos más tarde para reservar tu llamada.",
            "Your profile already fits. There are no free times right now: write to us later to book your call."),
    },
    close_repeat_withdrawn=bi("Has dejado la solicitud. Si quieres retomarla, escribe «continuar».",
                              "You have left the application. If you want to pick it up, write «continue»."),
    close_repeat_other=bi("Esta conversación ya está cerrada. Un reclutador revisará tu caso.",
                          "This conversation is closed. A recruiter will review your case."),
    notices={
        "human": bi("Soy Sofía, una asistente virtual: un reclutador revisará tu solicitud y podrá hablar contigo después.",
                    "I'm Sofía, a virtual assistant: a recruiter will review your application and can talk to you afterwards."),
        "pay": bi("Sobre el sueldo, te informará un reclutador.", "A recruiter will tell you about the pay."),
        "changed": bi("Hecho, lo he cambiado.", "Done, I've changed it."),
        "kept": bi("De acuerdo, lo dejo como estaba.", "OK, I'll leave it as it was."),
        "offtopic": bi("Eso no forma parte de mi función; sigamos con tu solicitud.",
                       "That's not part of my role; let's continue with your application."),
    },
    slots=SLOTS,
    cv=CV,
)
