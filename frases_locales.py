"""Repertorio local de frases inspiradoras (español).

Criterio: solo citas con atribución fiable (obras clásicas y discursos conocidos)
y proverbios populares anónimos. Se descartan las frases virales de autoría
dudosa. Las traducciones son libres, pensadas para leerse bien en el bocadillo.
"""

from __future__ import annotations

from typing import Dict, List

_DATOS = [
    # ---------------------------------------------------------------- Filosofía china
    ("Lao Tse", [
        "El viaje de mil millas comienza con un solo paso.",
        "Quien conoce a los demás es sabio; quien se conoce a sí mismo está iluminado.",
        "Quien domina a otros es fuerte; quien se domina a sí mismo es poderoso.",
        "La naturaleza no se apresura y, sin embargo, todo se cumple.",
        "Quien sabe no habla; quien habla no sabe.",
        "Nada hay más blando y débil que el agua, y sin embargo nada la supera para vencer lo duro.",
        "Un buen viajero no tiene planes fijos ni intención de llegar.",
        "Lo difícil se resuelve cuando aún es fácil; lo grande se hace cuando aún es pequeño.",
        "Quien sabe que tiene suficiente es rico.",
        "Un árbol que no podrías abarcar con los brazos nace de un diminuto brote.",
    ]),
    ("Confucio", [
        "No importa lo despacio que vayas, siempre que no te detengas.",
        "Aprender sin pensar es inútil; pensar sin aprender, peligroso.",
        "Lo que no quieras para ti, no lo quieras para los demás.",
        "Cuando veas a un hombre bueno, procura imitarlo; cuando veas a uno malo, examínate a ti mismo.",
        "La persona superior es modesta en sus palabras, pero la supera con sus actos.",
        "No te preocupes de que los demás no te conozcan; preocúpate de no conocerlos tú a ellos.",
        "Quien comete un error y no lo corrige, comete otro error mayor.",
        "Estudia el pasado si quieres definir el futuro.",
    ]),
    ("Sun Tzu", [
        "La suprema excelencia consiste en vencer al enemigo sin librar batalla.",
        "Conoce a tu enemigo y conócete a ti mismo: en cien batallas no correrás peligro.",
    ]),
    ("Guanzi", [
        "Si planeas para un año, siembra arroz; si planeas para diez, planta árboles; si planeas para cien, educa a las personas.",
    ]),
    # ---------------------------------------------------------------- Proverbios del mundo
    ("Proverbio chino", [
        "Quien mueve una montaña empieza apartando pequeñas piedras.",
        "El mejor momento para plantar un árbol fue hace veinte años. El segundo mejor momento es ahora.",
        "Cuando sopla el viento del cambio, unos construyen muros y otros molinos.",
        "Más vale encender una vela que maldecir la oscuridad.",
        "Quien pregunta es tonto cinco minutos; quien no pregunta, lo es toda la vida.",
        "Cuando el alumno está preparado, aparece el maestro.",
        "Cuando bebas agua, recuerda la fuente.",
        "Cuando el sabio señala la luna, el necio mira el dedo.",
        "Con paciencia y tiempo, la hoja de morera se convierte en seda.",
        "Una sola chispa puede incendiar toda la pradera.",
        "Un amigo cercano vale más que un pariente lejano.",
        "Un hombre sin sonrisa no debe abrir una tienda.",
        "Dime y lo olvido; enséñame y lo recuerdo; involúcrame y lo aprendo.",
    ]),
    ("Proverbio japonés", [
        "Cae siete veces, levántate ocho.",
        "Visión sin acción es un sueño; acción sin visión es una pesadilla.",
        "Hasta el mono se cae del árbol.",
        "El bambú que se dobla es más fuerte que el roble que resiste.",
    ]),
    ("Proverbio africano", [
        "Si quieres ir rápido, camina solo; si quieres llegar lejos, ve acompañado.",
        "Si no sabes adónde vas, mira de dónde vienes.",
        "Hace falta una aldea entera para educar a un niño.",
    ]),
    ("Proverbio árabe", [
        "La paciencia es la llave del alivio.",
    ]),
    ("Proverbio inglés", [
        "Roma no se construyó en un día.",
        "La práctica hace al maestro.",
    ]),
    ("Refrán popular", [
        "No hay mal que por bien no venga.",
        "A mal tiempo, buena cara.",
        "Más vale tarde que nunca.",
        "Poco a poco se anda lejos.",
        "El que la sigue, la consigue.",
        "Lo que bien se aprende, nunca se pierde.",
        "No dejes para mañana lo que puedas hacer hoy.",
        "De los errores también se aprende.",
        "Tras la tormenta sale el sol.",
        "Nunca es tarde si la dicha es buena.",
        "Quien algo quiere, algo le cuesta.",
        "Obras son amores, y no buenas razones.",
        "Al que madruga, Dios le ayuda.",
        "Cada cosa a su tiempo.",
        "Rectificar es de sabios.",
        "Querer es poder.",
        "La unión hace la fuerza.",
        "Cuando una puerta se cierra, otra se abre.",
        "El saber no ocupa lugar.",
        "Nadie nace sabiendo.",
        "Grano a grano hace la gallina el buche.",
        "Con paciencia y constancia se gana la batalla.",
        "Quien siembra, recoge.",
        "Lo importante no es caer, sino levantarse.",
        "El que persevera, alcanza.",
        "Quien no arriesga, no gana.",
        "Lo que mucho vale, mucho cuesta.",
        "Las prisas no son buenas consejeras.",
        "Todo llega a su tiempo para quien sabe esperar.",
        "Vísteme despacio, que tengo prisa.",
        "A quien buen árbol se arrima, buena sombra le cobija.",
        "La constancia vence lo que la dicha no alcanza.",
        "Lo bueno se hace esperar.",
        "Persevera y triunfarás.",
        "Con tiempo y paciencia, todo se consigue.",
    ]),
    ("Proverbio italiano", [
        "Quien va despacio va sano y va lejos.",
    ]),
    ("Proverbio turco", [
        "Ningún camino es largo con buena compañía.",
    ]),
    ("Proverbio ruso", [
        "Caer está permitido; levantarse es obligatorio.",
    ]),
    ("Proverbio popular", [
        "La hora más oscura es la que precede al amanecer.",
        "Si la vida te da limones, haz limonada.",
    ]),
    # ---------------------------------------------------------------- Mundo clásico
    ("Séneca", [
        "No es que tengamos poco tiempo, sino que perdemos mucho.",
        "La vida, si sabes usarla, es larga.",
        "Toda la vida hay que aprender a vivir.",
        "No hay viento favorable para quien no sabe a qué puerto se dirige.",
        "No nos atrevemos a muchas cosas porque son difíciles; pero son difíciles porque no nos atrevemos.",
        "Sufrimos más en la imaginación que en la realidad.",
        "No hay camino fácil de la tierra a las estrellas.",
    ]),
    ("Marco Aurelio", [
        "Lo que no beneficia al enjambre, no beneficia a la abeja.",
        "Lo que se interpone en el camino se convierte en el camino.",
        "La mejor venganza es no parecerse a quien te ofendió.",
        "Si algo es humanamente posible, considéralo también a tu alcance.",
        "El alma se tiñe del color de sus pensamientos.",
    ]),
    ("Epicteto", [
        "No son las cosas las que nos perturban, sino la opinión que tenemos de ellas.",
        "Primero di quién quieres ser y después haz lo que tengas que hacer.",
        "Ninguna cosa grande se crea de repente.",
    ]),
    ("Aristóteles", [
        "El principio es la mitad del todo.",
        "La raíz de la educación es amarga, pero su fruto es dulce.",
    ]),
    ("Will Durant", [
        "Somos lo que hacemos repetidamente. La excelencia, entonces, no es un acto, sino un hábito.",
    ]),
    ("Platón", [
        "El comienzo es la parte más importante del trabajo.",
    ]),
    ("Heráclito", [
        "Nadie se baña dos veces en el mismo río.",
        "Lo único permanente es el cambio.",
    ]),
    ("Sócrates", [
        "Una vida sin examen no merece ser vivida.",
        "Solo sé que no sé nada.",
    ]),
    ("Epicuro", [
        "No estropees lo que tienes deseando lo que no tienes.",
    ]),
    ("Horacio", [
        "Aprovecha el día y confía lo menos posible en el mañana.",
    ]),
    ("Virgilio", [
        "La fortuna favorece a los audaces.",
    ]),
    ("Cicerón", [
        "Mientras hay vida, hay esperanza.",
        "La gratitud no es solo la mayor de las virtudes, sino la madre de todas las demás.",
    ]),
    ("Ovidio", [
        "La gota cava la piedra, no con la fuerza, sino cayendo muchas veces.",
    ]),
    ("Plinio el Viejo", [
        "Casi todo parece imposible hasta que se hace.",
    ]),
    ("Terencio", [
        "Soy hombre; nada humano me es ajeno.",
    ]),
    ("Augusto", [
        "Apresúrate despacio.",
    ]),
    ("Buda", [
        "Todo lo que somos es el resultado de lo que hemos pensado.",
    ]),
    # ---------------------------------------------------------------- Literatura en español
    ("Miguel de Cervantes", [
        "Cada uno es artífice de su ventura.",
        "Donde una puerta se cierra, otra se abre.",
        "La diligencia es madre de la buena ventura.",
        "El que lee mucho y anda mucho, ve mucho y sabe mucho.",
        "La libertad, Sancho, es uno de los más preciosos dones que a los hombres dieron los cielos.",
        "Después de la tempestad viene la bonanza.",
    ]),
    ("Antonio Machado", [
        "Caminante, no hay camino, se hace camino al andar.",
        "Despacito y buena letra: el hacer las cosas bien importa más que el hacerlas.",
    ]),
    ("Gabriela Mistral", ["Hoy es siempre todavía."]),
    ("Frida Kahlo", ["Pies, ¿para qué los quiero si tengo alas para volar?"]),
    ("José Ortega y Gasset", ["Yo soy yo y mi circunstancia, y si no la salvo a ella no me salvo yo."]),
    ("Santiago Ramón y Cajal", ["Todo hombre puede ser, si se lo propone, escultor de su propio cerebro."]),
    ("Gabriel García Márquez", ["La vida no es la que uno vivió, sino la que uno recuerda y cómo la recuerda para contarla."]),
    ("Mario Benedetti", ["No te rindas, aún estás a tiempo de alcanzar y comenzar de nuevo."]),
    ("Fernando Pessoa", ["Todo vale la pena si el alma no es pequeña."]),
    ("Rainer Maria Rilke", ["Ten paciencia con todo lo que no está resuelto en tu corazón e intenta amar las preguntas mismas."]),
    ("Antoine de Saint-Exupéry", [
        "Lo esencial es invisible a los ojos.",
        "Solo con el corazón se puede ver bien.",
        "Es el tiempo que has perdido con tu rosa lo que hace a tu rosa tan importante.",
    ]),
    ("J. R. R. Tolkien", ["No todos los que vagan están perdidos."]),
    ("Dr. Seuss", ["Hoy eres tú, y eso es más verdad que la verdad. No hay nadie vivo más tú que tú."]),
    ("Oscar Wilde", ["Vivir es lo más raro del mundo: la mayoría de la gente existe, nada más."]),
    ("León Tolstói", ["Todos piensan en cambiar el mundo, pero nadie piensa en cambiarse a sí mismo."]),
    ("Johann W. Goethe", ["Conocer no es suficiente, hay que aplicar. Querer no es suficiente, hay que hacer."]),
    ("Voltaire", ["Lo mejor es enemigo de lo bueno."]),
    # ---------------------------------------------------------------- Pensadores y activistas
    ("Friedrich Nietzsche", [
        "Quien tiene un porqué para vivir encontrará casi siempre el cómo.",
        "Lo que no me mata me hace más fuerte.",
    ]),
    ("Søren Kierkegaard", ["La vida solo puede comprenderse hacia atrás, pero hay que vivirla hacia delante."]),
    ("Viktor Frankl", ["Cuando ya no podemos cambiar una situación, nos enfrentamos al reto de cambiarnos a nosotros mismos."]),
    ("Henry D. Thoreau", [
        "Si uno avanza con confianza en la dirección de sus sueños, se encontrará con un éxito inesperado en la vida cotidiana.",
        "No basta con estar ocupado: la pregunta es en qué.",
    ]),
    ("Ralph Waldo Emerson", ["Nada grande se ha logrado jamás sin entusiasmo."]),
    ("Nelson Mandela", [
        "Parece imposible hasta que se hace.",
        "El valor no es la ausencia de miedo, sino el triunfo sobre él.",
        "La educación es el arma más poderosa que puedes utilizar para cambiar el mundo.",
    ]),
    ("Martin Luther King Jr.", [
        "Si no puedes volar, corre; si no puedes correr, camina; si no puedes caminar, arrástrate; pero sigue adelante.",
        "La oscuridad no puede expulsar a la oscuridad: solo la luz puede hacerlo.",
    ]),
    ("Winston Churchill", ["Nunca cedáis, nunca, nunca, nunca."]),
    ("Eleanor Roosevelt", ["Nadie puede hacerte sentir inferior sin tu consentimiento."]),
    ("Theodore Roosevelt", [
        "Haz lo que puedas, con lo que tengas, donde estés.",
        "Nada en el mundo vale la pena si no implica esfuerzo, dolor y dificultad.",
    ]),
    ("Maya Angelou", ["Haz lo mejor que puedas hasta que sepas más; y cuando sepas más, hazlo mejor."]),
    ("Helen Keller", [
        "Solos podemos hacer tan poco; juntos podemos hacer mucho.",
        "El optimismo es la fe que conduce al logro.",
    ]),
    ("Anne Frank", ["Qué maravilloso es que nadie tenga que esperar ni un solo momento para empezar a mejorar el mundo."]),
    ("Malala Yousafzai", ["Un niño, un profesor, un libro y un lápiz pueden cambiar el mundo."]),
    # ---------------------------------------------------------------- Ciencia y creación
    ("Albert Einstein", [
        "La imaginación es más importante que el conocimiento.",
        "Lo importante es no dejar de hacerse preguntas.",
        "La vida es como montar en bicicleta: para mantener el equilibrio hay que seguir moviéndose.",
    ]),
    ("Marie Curie", [
        "En la vida no hay nada que temer, solo hay que comprender.",
    ]),
    ("Isaac Newton", ["Si he visto más lejos es porque estaba subido a hombros de gigantes."]),
    ("Louis Pasteur", ["En los campos de la observación, el azar solo favorece a las mentes preparadas."]),
    ("Thomas Edison", ["El genio es un uno por ciento de inspiración y un noventa y nueve por ciento de transpiración."]),
    ("Richard Feynman", [
        "El primer principio es no engañarte a ti mismo, y tú eres la persona más fácil de engañar.",
        "Lo que no puedo crear, no lo entiendo.",
    ]),
    ("Henry Ford", ["Tanto si crees que puedes como si crees que no puedes, tienes razón."]),
    ("Steve Jobs", [
        "Sigue hambriento, sigue siendo insensato.",
        "La única manera de hacer un gran trabajo es amar lo que haces.",
    ]),
    ("Michael Jordan", ["He fallado una y otra vez en mi vida, y por eso he tenido éxito."]),
    ("Muhammad Ali", ["No cuentes los días, haz que los días cuenten."]),
    ("John Lennon", ["La vida es aquello que te va sucediendo mientras te empeñas en hacer otros planes."]),
    # ---------------------------------------------------------------- Informática y seguridad
    ("Linus Torvalds", ["Hablar es barato. Enséñame el código."]),
    ("Grace Hopper", [
        "La frase más peligrosa del lenguaje es: «Siempre se ha hecho así».",
        "A veces es más fácil pedir perdón que pedir permiso.",
    ]),
    ("Alan Kay", ["La mejor manera de predecir el futuro es inventarlo."]),
    ("Alan Turing", ["Solo vemos un poco del futuro, pero lo suficiente para saber que hay mucho por hacer."]),
    ("Edsger Dijkstra", [
        "La simplicidad es un requisito previo para la fiabilidad.",
        "Probar un programa puede demostrar la presencia de errores, nunca su ausencia.",
    ]),
    ("Donald Knuth", ["La optimización prematura es la raíz de todos los males."]),
    ("Brian Kernighan", ["Depurar es el doble de difícil que escribir el código en primer lugar."]),
    ("Bruce Schneier", [
        "La seguridad es un proceso, no un producto.",
        "Cualquiera puede inventar un sistema de seguridad tan ingenioso que él mismo no sepa encontrarle fallos.",
    ]),
    ("Eric S. Raymond", ["Con suficientes ojos, todos los errores son fáciles de ver."]),
    ("Rob Pike", ["Un poco de copia es mejor que una pequeña dependencia."]),
]


def _construir() -> List[Dict[str, str]]:
    vistos = set()
    salida: List[Dict[str, str]] = []
    for autor, textos in _DATOS:
        for texto in textos:
            t = " ".join(texto.split())
            if t in vistos:
                continue
            vistos.add(t)
            salida.append({"texto": t, "autor": autor})
    return salida


FRASES: List[Dict[str, str]] = _construir()
