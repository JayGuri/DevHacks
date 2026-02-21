export const fadeInUp = {
    hidden: { opacity: 0, y: 16 },
    visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: 'easeOut' } }
}

export const fadeIn = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { duration: 0.25 } }
}

export const staggerContainer = {
    hidden: {},
    visible: { transition: { staggerChildren: 0.06 } }
}

export const slideInLeft = {
    hidden: { opacity: 0, x: -16 },
    visible: { opacity: 1, x: 0, transition: { duration: 0.3, ease: 'easeOut' } }
}

export const scaleIn = {
    hidden: { opacity: 0, scale: 0.95 },
    visible: { opacity: 1, scale: 1, transition: { duration: 0.2, ease: 'easeOut' } }
}

export const cardHover = {
    rest: { scale: 1, boxShadow: '0 0 0 0 transparent' },
    hover: { scale: 1.01, boxShadow: '0 4px 24px -4px rgba(0,0,0,0.15)', transition: { duration: 0.2 } }
}
