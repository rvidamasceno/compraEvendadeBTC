import flet as ft
import requests
import pandas as pd
import ta
from datetime import datetime
import asyncio
from typing import Optional
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import BytesIO
import base64
import tracemalloc

# Iniciar tracemalloc
tracemalloc.start()

class BitcoinTrader:
    def __init__(self):
        self.base_url = "https://api.binance.com/api/v3"
        
    def get_bitcoin_price(self) -> float:
        """Obtém o preço atual do Bitcoin"""
        response = requests.get(f"{self.base_url}/ticker/price", params={"symbol": "BTCUSDT"})
        return float(response.json()["price"])
    
    def get_historical_data(self) -> pd.DataFrame:
        """Obtém dados históricos para análise"""
        response = requests.get(
            f"{self.base_url}/klines",
            params={
                "symbol": "BTCUSDT",
                "interval": "1h",
                "limit": 200  # Aumentado para 200 para calcular MM200
            }
        )
        
        df = pd.DataFrame(response.json(), columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        df['close'] = pd.to_numeric(df['close'])
        return df

    def analyze_market(self) -> dict:
        """Analisa o mercado e retorna sinais de compra/venda"""
        df = self.get_historical_data()
        
        df['SMA20'] = ta.trend.sma_indicator(df['close'], window=20)
        df['SMA50'] = ta.trend.sma_indicator(df['close'], window=50)
        df['SMA200'] = ta.trend.sma_indicator(df['close'], window=200)  # Para o Mayer Multiple
        df['RSI'] = ta.momentum.rsi(df['close'], window=14)
        
        current_price = float(df['close'].iloc[-1])
        sma20 = float(df['SMA20'].iloc[-1])
        sma50 = float(df['SMA50'].iloc[-1])
        sma200 = float(df['SMA200'].iloc[-1])
        rsi = float(df['RSI'].iloc[-1])
        
        # Calcular o Mayer Multiple
        mayer_multiple = current_price / sma200
        
        return {
            'price': current_price,
            'sma20': sma20,
            'sma50': sma50,
            'rsi': rsi,
            'mayer_multiple': mayer_multiple
        }

    def get_trading_signal(self, analysis: dict) -> tuple:
        """Gera sinais de trading baseados na análise"""
        signal = "AGUARDAR"
        reasons = []
        
        # Adicionar lógica do Mayer Multiple
        if analysis['mayer_multiple'] < 0.85:
            signal = "COMPRAR"
            reasons.append("Mayer Multiple abaixo de 0.85 (subvalorizado)")
        elif analysis['mayer_multiple'] > 2.4:
            signal = "VENDER"
            reasons.append("Mayer Multiple acima de 2.4 (sobrevalorizado)")
        
        if analysis['rsi'] < 30:
            signal = "COMPRAR"
            reasons.append("RSI indica sobrevendido")
        
        if analysis['price'] < analysis['sma20'] < analysis['sma50']:
            signal = "COMPRAR"
            reasons.append("Preço abaixo das médias móveis")
            
        if analysis['rsi'] > 70:
            signal = "VENDER"
            reasons.append("RSI indica sobrecomprado")
            
        if analysis['price'] > analysis['sma20'] > analysis['sma50']:
            signal = "VENDER"
            reasons.append("Preço acima das médias móveis")
            
        return signal, reasons

class BitcoinTraderUI:
    def __init__(self, page: ft.Page):
        self.page = page
        self.trader = BitcoinTrader()
        self.setup_page()
        self.create_widgets()
        self.running = False  # Inicialmente False
        
    async def initialize(self):
        """Método de inicialização assíncrona"""
        self.running = True
        await self.update_data()  # Primeira atualização
        asyncio.create_task(self.auto_update_loop())  # Inicia o loop de atualização

    def setup_page(self):
        self.page.title = "Bitcoin Trader"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 20
        self.page.window_width = 1200  # Aumentado para acomodar o gráfico
        self.page.window_height = 800
        self.page.update()

    def create_chart(self, df: pd.DataFrame) -> ft.Image:
        # Criar subplots: preço+MM em cima, RSI e Mayer Multiple embaixo
        fig = make_subplots(rows=3, cols=1, 
                           shared_xaxes=True,
                           vertical_spacing=0.05,
                           row_heights=[0.5, 0.25, 0.25])

        # Gráfico de preço e médias móveis
        fig.add_trace(
            go.Scatter(x=df.index, y=df['close'], name='Preço', line=dict(color='#ffffff')),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=df['SMA20'], name='SMA20', line=dict(color='#1976D2')),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=df['SMA50'], name='SMA50', line=dict(color='#FFA726')),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(x=df.index, y=df['SMA200'], name='SMA200', line=dict(color='#E53935')),
            row=1, col=1
        )

        # Gráfico do RSI
        fig.add_trace(
            go.Scatter(x=df.index, y=df['RSI'], name='RSI', line=dict(color='#4CAF50')),
            row=2, col=1
        )
        # Adicionar linhas de sobrecomprado/sobrevendido
        fig.add_hline(y=70, line_dash="dash", line_color="red", row=2, col=1)
        fig.add_hline(y=30, line_dash="dash", line_color="green", row=2, col=1)

        # Gráfico do Mayer Multiple
        mayer_multiple = df['close'] / df['SMA200']
        fig.add_trace(
            go.Scatter(x=df.index, y=mayer_multiple, name='Mayer Multiple', line=dict(color='#9C27B0')),
            row=3, col=1
        )
        # Adicionar linhas de referência do Mayer Multiple
        fig.add_hline(y=2.4, line_dash="dash", line_color="red", row=3, col=1)
        fig.add_hline(y=0.85, line_dash="dash", line_color="green", row=3, col=1)

        # Atualizar layout com tamanho menor
        fig.update_layout(
            template='plotly_dark',
            height=400,  # Reduzido de 600 para 400
            width=600,   # Definido width explicitamente
            margin=dict(l=10, r=10, t=20, b=10),
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        # Atualizar eixos Y
        fig.update_yaxes(title_text="Preço (USD)", row=1, col=1)
        fig.update_yaxes(title_text="RSI", row=2, col=1)
        fig.update_yaxes(title_text="Mayer Multiple", row=3, col=1)

        # Converter para imagem base64
        img_bytes = BytesIO()
        fig.write_image(img_bytes, format="png")
        img_bytes.seek(0)
        img_base64 = base64.b64encode(img_bytes.read()).decode()

        return ft.Image(
            src_base64=img_base64,
            width=600,  # Reduzido para 600
            height=400, # Reduzido para 400
            fit=ft.ImageFit.CONTAIN,
        )

    def create_widgets(self):
        # Título
        self.title = ft.Text(
            "Bitcoin Trader Dashboard",
            size=32,
            weight=ft.FontWeight.BOLD,
            color=ft.colors.BLUE_400
        )

        # Área do gráfico
        self.chart_container = ft.Container(
            content=ft.Text("Carregando gráfico..."),
            alignment=ft.alignment.center,
        )

        # Preço atual
        self.price_text = ft.Text(
            "Carregando...",
            size=24,
            color=ft.colors.GREEN_400
        )

        # Indicadores
        self.sma20_text = ft.Text(size=16)
        self.sma50_text = ft.Text(size=16)
        self.rsi_text = ft.Text(size=16)
        self.mayer_multiple_text = ft.Text(size=16)

        # Sinal de trading
        self.signal_text = ft.Text(
            size=20,
            weight=ft.FontWeight.BOLD
        )

        # Razões
        self.reasons_text = ft.Text(size=16)

        # Última atualização
        self.last_update_text = ft.Text(
            size=14,
            color=ft.colors.GREY_400
        )

        # Adicionar texto de autoria
        self.author_text = ft.Text(
            "Desenvolvido por Ravi Damasceno",
            size=12,
            color=ft.colors.GREY_400,
            italic=True,
            text_align=ft.TextAlign.RIGHT
        )

        # Botão de atualização
        self.update_button = ft.ElevatedButton(
            "Atualizar",
            on_click=lambda e: asyncio.create_task(self.update_data()),
            icon=ft.icons.REFRESH
        )

        # Layout em duas colunas principais
        self.main_row = ft.Row(
            controls=[
                # Coluna da esquerda (gráfico)
                ft.Column(
                    controls=[
                        self.chart_container,
                    ],
                    width=600,  # Largura fixa para o gráfico
                ),
                # Coluna da direita (informações)
                ft.Column(
                    controls=[
                        self.price_text,
                        ft.Text("Indicadores Técnicos:", size=20, weight=ft.FontWeight.BOLD),
                        self.sma20_text,
                        self.sma50_text,
                        self.rsi_text,
                        self.mayer_multiple_text,
                        self.signal_text,
                        self.reasons_text,
                    ],
                    spacing=10,
                    expand=True,  # Expande para ocupar o espaço restante
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            spacing=20,
        )

        # Container principal
        self.main_container = ft.Container(
            content=ft.Column(
                controls=[
                    self.title,
                    ft.Divider(),
                    self.main_row,
                    ft.Row(
                        controls=[
                            self.last_update_text,
                            ft.Container(width=20),  # Espaçamento
                            self.author_text
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ],
                spacing=20,
            ),
            padding=20,
            border_radius=10,
            border=ft.border.all(1, ft.colors.BLUE_GREY_400),
        )

        self.page.add(self.main_container)
        self.page.on_close = self.cleanup
        asyncio.create_task(self.initialize())

    def update_display(self, analysis: dict, signal: str, reasons: list):
        self.price_text.value = f"Preço Bitcoin: ${analysis['price']:,.2f}"
        self.sma20_text.value = f"SMA 20: ${analysis['sma20']:,.2f}"
        self.sma50_text.value = f"SMA 50: ${analysis['sma50']:,.2f}"
        self.rsi_text.value = f"RSI: {analysis['rsi']:.2f}"
        self.mayer_multiple_text.value = f"Mayer Multiple: {analysis['mayer_multiple']:.3f}"
        
        # Colorir o Mayer Multiple baseado em seus valores
        if analysis['mayer_multiple'] < 0.85:
            self.mayer_multiple_text.color = ft.colors.GREEN_400
        elif analysis['mayer_multiple'] > 2.4:
            self.mayer_multiple_text.color = ft.colors.RED_400
        else:
            self.mayer_multiple_text.color = ft.colors.WHITE
        
        self.signal_text.value = f"Sinal: {signal}"
        self.signal_text.color = (
            ft.colors.GREEN_400 if signal == "COMPRAR"
            else ft.colors.RED_400 if signal == "VENDER"
            else ft.colors.GREY_400
        )
        
        self.reasons_text.value = "Razões:\n" + "\n".join(f"• {reason}" for reason in reasons)
        self.last_update_text.value = f"Última atualização: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.page.update()

    async def update_data(self):
        try:
            analysis = self.trader.analyze_market()
            signal, reasons = self.trader.get_trading_signal(analysis)
            
            # Obter dados históricos para o gráfico
            df = self.trader.get_historical_data()
            df.set_index(pd.to_datetime(df['timestamp'], unit='ms'), inplace=True)
            
            # Calcular indicadores para o gráfico
            df['SMA20'] = ta.trend.sma_indicator(df['close'], window=20)
            df['SMA50'] = ta.trend.sma_indicator(df['close'], window=50)
            df['SMA200'] = ta.trend.sma_indicator(df['close'], window=200)
            df['RSI'] = ta.momentum.rsi(df['close'], window=14)
            
            # Atualizar o gráfico
            self.chart_container.content = self.create_chart(df)
            
            # Atualizar os outros widgets
            self.update_display(analysis, signal, reasons)
            
        except Exception as e:
            self.signal_text.value = f"Erro ao atualizar: {str(e)}"
            self.page.update()

    async def auto_update_loop(self):
        while self.running:
            try:
                await self.update_data()
                await asyncio.sleep(60)  # Atualiza a cada 60 segundos
            except Exception as e:
                print(f"Erro no loop de atualização: {e}")
                await asyncio.sleep(5)  # Espera um pouco antes de tentar novamente

    def cleanup(self):
        """Método para limpeza ao fechar"""
        self.running = False
        tracemalloc.stop()

async def main(page: ft.Page):
    app = BitcoinTraderUI(page)
    page.on_close = app.cleanup
    await app.initialize()

if __name__ == "__main__":
    ft.app(target=main)





