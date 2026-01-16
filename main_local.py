import customtkinter as ctk
import threading
import pyautogui
import cv2
import numpy as np
import time
import ctypes
import os
import traceback

# --- AJUSTE DE PRECISÃO DPI PARA WINDOWS ---
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

class BotEverskies:
    def __init__(self):
        self.rodando = False
        self.pasta_raiz = os.path.dirname(os.path.abspath(__file__))
        
        self.config = {
            'verso': os.path.join(self.pasta_raiz, 'verso.png'),
            'verso_pequeno': os.path.join(self.pasta_raiz, 'verso_pequeno.png'),
            'fim': os.path.join(self.pasta_raiz, 'fim_de_jogo.png'),
            'replay': os.path.join(self.pasta_raiz, 'botao_novo_jogo.png'),
            'play_again': os.path.join(self.pasta_raiz, 'jogar_denovo_botao.png'),
            'precisao': 0.7,
            'precisao_par_base': 0.7, 
            'animacao': 0.1,
            'delay_reset': 0.2 
        }
        
        self.verso_atual = self.config['verso']
        self.regiao_canvas = None 
        
        # --- VARIÁVEIS PARA PRECISÃO DINÂMICA (BOT IMPACIENTE) ---
        self.tentativas_mesmo_tabuleiro = 0
        self.ultimo_total_cartas = 0
        self.precisao_par_atual = self.config['precisao_par_base']
        
        # --- CONTADOR DE ESTÁGIOS ---
        self.estagio = 1

        # --- LÓGICA DE MATRIZ ESTÁTICA ---
        self.lista_alvos = []
        self.w_carta = 0
        self.h_carta = 0
        self.watchdog_time = time.time()
        self.f5_watchdog_time = time.time() # Timer para detectar travamento total

    def log(self, mensagem):
        app.adicionar_log(mensagem)

    def converter_para_grid(self, cartas):
        if not cartas: 
            return {}
            
        def agrupar(lista):
            if not lista: 
                return []
            ord = sorted(lista)
            grupos = [ord[0]]
            for x in ord[1:]:
                if x - grupos[-1] > 25: 
                    grupos.append(x)
            return grupos
            
        gy = agrupar([c[1] for c in cartas])
        gx = agrupar([c[0] for c in cartas])
        
        mapping = {}
        for c in cartas:
            r = next((i+1 for i, y in enumerate(gy) if abs(c[1]-y) <= 25), 0)
            col = next((i+1 for i, x in enumerate(gx) if abs(c[0]-x) <= 25), 0)
            mapping[c] = (r, col)
        return mapping

    def localizar_cartas(self):
        try:
            res_pequeno = pyautogui.locateOnScreen(self.config['verso_pequeno'], confidence=0.7)
            if res_pequeno is not None:
                self.verso_atual = self.config['verso_pequeno']
            else:
                self.verso_atual = self.config['verso']
        except (pyautogui.ImageNotFoundException, Exception):
            self.verso_atual = self.config['verso']

        screenshot = pyautogui.screenshot()
        screenshot_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        template = cv2.imread(self.verso_atual)
        
        if template is None:
            raise FileNotFoundError(f"Não foi possível carregar {self.verso_atual}")
            
        w, h = template.shape[1], template.shape[0]
        res = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
        locais = np.where(res >= self.config['precisao'])
        
        coords = []
        for pt in zip(*locais[::-1]):
            if not any(abs(pt[0] + w//2 - c[0]) < 40 and abs(pt[1] + h//2 - c[1]) < 40 for c in coords):
                coords.append((pt[0] + w//2, pt[1] + h//2))
        
        coords.sort(key=lambda x: (x[1], x[0]))
        return coords, w, h

    def resolver_rodada(self):
        tempo_maximo = app.get_valor_config('watchdog_time')
        
        # --- LÓGICA DE ATUALIZAÇÃO F5 (120s SEM AÇÃO) ---
        if time.time() - self.f5_watchdog_time > 120:
            self.log("Inatividade detectada (120s). Atualizando página (F5)...")
            pyautogui.press('f5')
            self.f5_watchdog_time = time.time()
            self.lista_alvos = []
            time.sleep(5) # Espera carregar
            return False

        if self.lista_alvos and (time.time() - self.watchdog_time > tempo_maximo):
            self.log(f"Watchdog: Resetando matriz ({tempo_maximo}s)")
            self.lista_alvos = []

        if not self.lista_alvos:
            cartas, w, h = self.localizar_cartas()
            if not cartas: 
                return False
                
            self.lista_alvos = cartas
            self.w_carta = w
            self.h_carta = h
            self.watchdog_time = time.time()
            self.log(f"Matriz mapeada: {len(self.lista_alvos)} cartas.")
        
        cartas = self.lista_alvos
        w, h = self.w_carta, self.h_carta

        if len(cartas) == 2:
            self.log("Finalizando estágio: Clicando no último par.")
            pyautogui.click(cartas[0])
            time.sleep(0.5)
            pyautogui.click(cartas[1])
            self.lista_alvos = []
            self.f5_watchdog_time = time.time() # Reset por ação bem sucedida
            return True

        if len(cartas) == self.ultimo_total_cartas:
            self.tentativas_mesmo_tabuleiro += 1
        else:
            self.ultimo_total_cartas = len(cartas)
            self.watchdog_time = time.time()
            self.tentativas_mesmo_tabuleiro = 0 
            self.precisao_par_atual = self.config['precisao_par_base']

        if self.tentativas_mesmo_tabuleiro >= 1:
            valor_queda = app.get_valor_config('reducao_precisao')
            self.precisao_par_atual = max(0.5, self.config['precisao_par_base'] - (valor_queda * self.tentativas_mesmo_tabuleiro))

        if len(cartas) % 2 != 0:
            self.lista_alvos = [] 
            return False

        grid_map = self.converter_para_grid(cartas)
        memoria = [] 
        resolvidas = []
        img_v = cv2.resize(cv2.imread(self.verso_atual, 0), (15, 15)).astype('float32')
        
        tamanho_lote_pares = int(app.get_valor_config('lote_pares'))
        cartas_por_lote = tamanho_lote_pares * 2

        for i in range(0, len(cartas), 2):
            if not self.rodando: break
            dupla = cartas[i:i+2]
            for pos in dupla:
                if any(abs(pos[0] - r[0]) < 10 and abs(pos[1] - r[1]) < 10 for r in resolvidas): continue
                pyautogui.click(pos)
                self.f5_watchdog_time = time.time() # Reset por clique
                assinatura_atual = None
                for _ in range(7):
                    time.sleep(self.config['animacao'])
                    try:
                        foto = pyautogui.screenshot(region=(int(pos[0]-w/2), int(pos[1]-h/2), w, h))
                        foto_cv = cv2.resize(cv2.cvtColor(np.array(foto), cv2.COLOR_RGB2GRAY), (15, 15)).astype('float32')
                        if cv2.matchTemplate(foto_cv, img_v, cv2.TM_CCOEFF_NORMED)[0][0] < 0.80:
                            assinatura_atual = foto_cv
                            break
                    except: continue
                memoria.append({'assinatura': assinatura_atual, 'posicao': pos, 'grid_pos': grid_map[pos]})

            time.sleep(self.config['delay_reset'])

            if (len(memoria) >= cartas_por_lote) or (i + 2 >= len(cartas)):
                par_encontrado = True
                while par_encontrado:
                    par_encontrado = False
                    for idx_a in range(len(memoria)):
                        for idx_b in range(idx_a + 1, len(memoria)):
                            if memoria[idx_a]['assinatura'] is None or memoria[idx_b]['assinatura'] is None: continue
                            res = cv2.matchTemplate(memoria[idx_a]['assinatura'], memoria[idx_b]['assinatura'], cv2.TM_CCOEFF_NORMED)
                            if res[0][0] > self.precisao_par_atual:
                                pyautogui.click(memoria[idx_a]['posicao'])
                                time.sleep(0.1)
                                pyautogui.click(memoria[idx_b]['posicao'])
                                p1, p2 = memoria[idx_a]['posicao'], memoria[idx_b]['posicao']
                                resolvidas.extend([p1, p2])
                                self.lista_alvos = [c for c in self.lista_alvos if c != p1 and c != p2]
                                memoria.pop(idx_b); memoria.pop(idx_a)
                                par_encontrado = True
                                self.watchdog_time = time.time()
                                self.f5_watchdog_time = time.time() # Reset por par resolvido
                                time.sleep(1.2 + self.config['delay_reset'])
                                break
                        if par_encontrado: break
        return True

    def loop_principal(self):
        self.config['precisao_par_base'] = app.get_valor_config('precisao_base')
        self.config['animacao'] = app.get_valor_config('vel_animacao')
        self.precisao_par_atual = self.config['precisao_par_base']
        self.log(f"Iniciando estágio {self.estagio}...")
        time.sleep(3)
        
        while self.rodando:
            try:
                # --- CHECK 1: BOTÃO 'JOGAR DENOVO' (RESET) ---
                try:
                    pos_play_again = pyautogui.locateCenterOnScreen(self.config['play_again'], confidence=0.7)
                    if pos_play_again:
                        self.log("Botão 'Jogar de Novo' detectado! Reiniciando no Estágio 1.")
                        pyautogui.click(pos_play_again)
                        self.estagio = 1
                        self.lista_alvos = []; self.tentativas_mesmo_tabuleiro = 0; self.ultimo_total_cartas = 0
                        self.f5_watchdog_time = time.time()
                        time.sleep(app.get_valor_config('delay_replay'))
                        continue
                except: pass

                # --- CHECK 2: FIM DE ESTÁGIO ---
                fim_detectado = False
                try:
                    if pyautogui.locateOnScreen(self.config['fim'], confidence=0.7, grayscale=True) is not None:
                        fim_detectado = True
                except: pass

                if fim_detectado:
                    # --- NOVA LÓGICA: LIMITADOR DE ESTÁGIO ---
                    limite_escolhido = int(app.get_valor_config('limite_estagio'))
                    if self.estagio >= limite_escolhido:
                        self.log(f"Limite de estágio {limite_escolhido} atingido. Reiniciando jogatina...")
                        time.sleep(3)
                        try:
                            # Tenta clicar no botão de reset final (jogar de novo)
                            pos_reset_final = pyautogui.locateCenterOnScreen(self.config['play_again'], confidence=0.7)
                            if pos_reset_final:
                                pyautogui.click(pos_reset_final)
                                self.estagio = 1
                                self.lista_alvos = []
                                continue
                        except: pass

                    self.log(f"Fim de estágio {self.estagio}!")
                    time.sleep(1)
                    try:
                        pos_replay = pyautogui.locateCenterOnScreen(self.config['replay'], confidence=0.7)
                        if pos_replay: 
                            pyautogui.click(pos_replay)
                            self.estagio += 1
                            self.lista_alvos = []; self.tentativas_mesmo_tabuleiro = 0; self.ultimo_total_cartas = 0
                            time.sleep(app.get_valor_config('delay_replay'))
                            continue
                    except: pass
                
                if not self.resolver_rodada(): time.sleep(1)
            except Exception: time.sleep(2)
            time.sleep(1)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.bot = BotEverskies()
        self.title("Everskies Memory Bot v5.0")
        self.geometry("500x820")
        ctk.set_appearance_mode("dark")
        self.tabview = ctk.CTkTabview(self, width=480, height=790)
        self.tabview.pack(padx=10, pady=10)
        self.tab_main = self.tabview.add("Console")
        self.tab_config = self.tabview.add("Configurações")
        self.setup_main_tab(); self.setup_config_tab()

    def setup_main_tab(self):
        ctk.CTkLabel(self.tab_main, text="Status do Bot", font=("Roboto", 24, "bold")).pack(pady=20)
        ctk.CTkButton(self.tab_main, text="INICIAR BOT", fg_color="#2ecc71", command=self.start_bot).pack(pady=10)
        ctk.CTkButton(self.tab_main, text="PARAR BOT", fg_color="#e74c3c", command=self.stop_bot).pack(pady=10)
        self.textbox = ctk.CTkTextbox(self.tab_main, width=420, height=380, font=("Consolas", 12)); self.textbox.pack(pady=20)

    def setup_config_tab(self):
        self.inputs = {}
        configs = [
            ("Precisão Base", "precisao_base", "0.7"),
            ("Queda Precisão", "reducao_precisao", "0.1"),
            ("Vel. Animação (seg)", "vel_animacao", "0.1"),
            ("Delay após Replay (seg)", "delay_replay", "1.5"),
            ("Watchdog Timer (seg)", "watchdog_time", "10.0"),
            ("Tamanho do Lote (Pares)", "lote_pares", "3"),
            ("Limite de Estágio", "limite_estagio", "30") # NOVO CAMPO
        ]
        for label_text, key, default in configs:
            frame = ctk.CTkFrame(self.tab_config); frame.pack(fill="x", padx=20, pady=10)
            ctk.CTkLabel(frame, text=label_text, width=220, anchor="w").pack(side="left", padx=10)
            entry = ctk.CTkEntry(frame, width=80); entry.insert(0, default); entry.pack(side="right", padx=10)
            self.inputs[key] = entry

    def get_valor_config(self, key):
        try: return float(self.inputs[key].get())
        except: return 0.1

    def adicionar_log(self, texto):
        self.textbox.insert("end", f"[{time.strftime('%H:%M:%S')}] {texto}\n"); self.textbox.see("end")

    def start_bot(self):
        if not self.bot.rodando:
            self.bot.rodando = True
            threading.Thread(target=self.bot.loop_principal, daemon=True).start()

    def stop_bot(self): self.bot.rodando = False

if __name__ == "__main__":
    app = App(); app.mainloop()