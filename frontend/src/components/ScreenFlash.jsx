import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

export default function ScreenFlash({ trigger, color = '#ef4444' }) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (trigger) {
      setShow(true);
      const t = setTimeout(() => setShow(false), 400);
      return () => clearTimeout(t);
    }
  }, [trigger]);

  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0.35 }}
          animate={{ opacity: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4, ease: 'easeOut' }}
          className="fixed inset-0 z-[90] pointer-events-none"
          style={{
            background: `radial-gradient(ellipse at center, ${color}25 0%, transparent 70%)`,
            mixBlendMode: 'screen',
          }}
        />
      )}
    </AnimatePresence>
  );
}
