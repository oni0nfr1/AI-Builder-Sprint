import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // getUserMedia는 보안 컨텍스트를 요구한다. localhost는 예외로 허용되지만
    // 다른 기기에서 접속해 테스트하려면 https가 필요하다.
    host: true,
  },
});
