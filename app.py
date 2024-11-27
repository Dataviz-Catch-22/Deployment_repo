import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
#import plotly.express as px
from pymongo import MongoClient
import config
from flask_caching import Cache

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

# Set up caching
cache = Cache(app.server, config={'CACHE_TYPE': 'simple'})

# MongoDB client setup
client = MongoClient(config.MONGO_CLOUD_URI)

# Ticker options with descriptions
ticker_options = {
    "SPY": "Overall Market (S&P 500)",
    "AAPL": "Apple Inc.",
    "DIA": "Dow Jones Industrial Average",
    "VNQ": "Real Estate (Vanguard Real Estate ETF)",
    "XLE": "Energy Sector",
    "XLF": "Financial Sector",
    "XLK": "Technology Sector",
    "XLU": "Utilities Sector",
    "XLV": "Healthcare Sector",
    "XLY": "Consumer Discretionary Sector",
    "IWM": "Russell 2000 Index ETF",
    "QQQ": "Nasdaq-100 Index ETF"
}

def align_data(stock_data, infections_df, cutoff_date="2022-07-08"):
    last_date = min(stock_data.index.max(), pd.to_datetime(cutoff_date))
    return stock_data[stock_data.index <= last_date], infections_df[infections_df.index <= last_date]

# Load events data and format with <br> for better tooltip readability
@cache.memoize(timeout=3600)
def load_events_from_mongodb():
    db = client["data"]
    collection = db["covid-19_timeline"]
    events = list(collection.find({}))
    if events:
        df_events = pd.DataFrame(events)
        df_events['date'] = pd.to_datetime(df_events['date'], format="%B %d, %Y")
        df_events.set_index('date', inplace=True)
        df_events.sort_index(inplace=True)
        df_events['event_text'] = df_events['news'].apply(
            lambda x: "<br>".join(x) if isinstance(x, list) else "No event"
        )
        return df_events[['event_text']]
    return pd.DataFrame()

# Load COVID event and infection data
@cache.memoize(timeout=3600)
def load_infection_data_from_mongodb():
    db = client["data"]
    collection = db["covid-19_infections"]
    data = list(collection.find({"iso_code": "USA"}))
    df_infections = pd.DataFrame(data) if data else pd.DataFrame()
    if not df_infections.empty:
        df_infections['date'] = pd.to_datetime(df_infections['date'])
        df_infections.set_index('date', inplace=True)
    return df_infections

# Load selected stock data
@cache.memoize(timeout=3600)
def load_stock_data(ticker):
    db = client["data"]
    collection = db[f"{ticker}_1Day"]
    data = list(collection.find({"symbol": ticker}))
    df = pd.DataFrame(data) if data else pd.DataFrame()
    if not df.empty:
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df.set_index('timestamp', inplace=True)
    return df

# Normalize stock data
def normalize_stock_data(data):
    if not data.empty:
        first_close_price = data['close'].iloc[0]
        data['indexed_close'] = (data['close'] / first_close_price) * 100
        data.iloc[0, data.columns.get_loc('indexed_close')] = 100
    return data

@cache.memoize(timeout=3600)
def load_all_data():
    # Load events data
    events_df = load_events_from_mongodb()
    
    # Load infection data
    infections_df = load_infection_data_from_mongodb()
    
    # Load stock data for all tickers
    stock_data = {}
    for ticker in ticker_options.keys():
        stock_data[ticker] = normalize_stock_data(load_stock_data(ticker))
        
    return events_df, infections_df, stock_data

events_df, covid_infections, stock_data = load_all_data()

# Function to break long events into multiple lines
def split_event_text(event_text, line_length=100):
        words = event_text.split(' ')
        lines = []
        line = ""
        for word in words:
            # If adding this word exceeds the line length, start a new line
            if len(line + word) > line_length:
                lines.append(line)
                line = word
            else:
                if line:
                    line += ' ' + word
                else:
                    line = word
        if line:  # Add the last line if it exists
            lines.append(line)
        return "<br>".join(lines)

def create_dual_axis_chart(stock_data, covid_infections, ticker_names, events_df):
    fig = go.Figure()

    # Find the latest date in the events dataframe to use as the cutoff
    cutoff_date = events_df.index.max()

    # Stock data line chart for each selected ticker, filtered up to the cutoff date
    for ticker, data in stock_data.items():
        filtered_data = data[data.index <= cutoff_date]
        fig.add_trace(go.Scatter(
            x=filtered_data.index,
            y=filtered_data['indexed_close'],
            mode='lines',
            name=ticker_names[ticker],
            line=dict(width=2),
            yaxis='y1',  # Primary y-axis
            visible=True  # Ensure all selected tickers are visible
        ))



    # Plot events as invisible markers for hover tooltip display
    fig.add_trace(go.Scatter(
        x=events_df.index,
        y=[100] * len(events_df),  # Ensures events align with the primary y-axis
        mode='markers',
        name='Event',
        customdata=[split_event_text(event) for event in events_df['event_text']],
        marker=dict(color='blue', size=8, opacity=0),  # Invisible markers
        hovertemplate="<b>Event:</b><br>%{customdata}<extra></extra>"
    ))

    # COVID-19 cases bar chart on secondary y-axis, filtered up to the cutoff date
    filtered_covid_infections = covid_infections[covid_infections.index <= cutoff_date]
    fig.add_trace(go.Bar(
        x=filtered_covid_infections.index,
        y=filtered_covid_infections['new_cases_smoothed'],
        name='COVID-19 Cases (Smoothed)',
        marker=dict(color='red', opacity=0.4),
        yaxis='y2'  # Secondary y-axis
    ))

    # Layout with dual axes
    fig.update_layout(
        title="Indexed Close Price and COVID-19 Cases",
        xaxis=dict(title='Date', range=[stock_data[list(stock_data.keys())[0]].index.min(), cutoff_date]),  # Set range up to cutoff date
        yaxis=dict(title='Indexed Price (%)', side='left', showgrid=True),
        yaxis2=dict(title='COVID-19 Cases (Smoothed)', overlaying='y', side='right', showgrid=False),
        hovermode='x unified',
        template='plotly_white',
          hoverlabel=dict(
            bordercolor="white",  # Border around tooltip for clearer visibility
            font=dict(family="Arial, sans-serif", size=12, color="black"),  # Font styling
            align="left",  # Align text to the left inside the tooltip
            namelength=0,  # Hide name in the tooltip
            # Word wrapping is handled automatically by Plotly
        )
    )

    return fig


# Layout
app.layout = html.Div([  
    dbc.Row([  
        dbc.Col([  
            html.H1("The Economic Story of COVID", style={'textAlign': 'center', 'color': 'black'}),
            dcc.Checklist(
                id='colorblind-toggle',
                options=[
                    {'label': 'Colorblind Friendly Mode', 'value': 'colorblind'}
                ],
                value=[],  # Default value (empty means standard mode)
                inline= True
            ),  
            dcc.Dropdown(  
                id='ticker-dropdown',  
                options=[{'label': name, 'value': ticker} for ticker, name in ticker_options.items()],  
                value=['SPY'],  # Default selection  
                multi=True,  
                placeholder="Select one or more tickers",  
                style={'backgroundColor': 'white', 'color': 'black'}  
            ),  
            dcc.Graph(id='line-chart', style={'height': '60vh', 'marginBottom' : '0px'}),
            dcc.Store(id='hover-store'),
            html.Div(id='heatmap-container', style={'height': '10vh', 'marginTop': '0px'})  
        ])  
    ]),  
], style={'backgroundColor': 'white', 'color': 'black'})  

# Line chart callback
@app.callback(
    Output('line-chart', 'figure'),
    [Input('ticker-dropdown', 'value'),
     Input('colorblind-toggle', 'value')]
)
def update_line_chart(tickers, colorblind_mode):
    # Use the cached data for all tickers
    events_df, covid_infections, stock_data = load_all_data()

    # Filter the stock data for the selected tickers
    selected_stock_data = {ticker: stock_data[ticker] for ticker in tickers}
    ticker_names = {ticker: ticker_options.get(ticker, ticker) for ticker in tickers}

    if 'colorblind' in colorblind_mode:
        colors = qualitative.Safe  # Colorblind-friendly palette
    else:
        colors = qualitative.Plotly

    # Create the figure with the selected stock data
    fig = go.Figure()

    # Find the latest date in the events dataframe to use as the cutoff
    cutoff_date = events_df.index.max()

    # Stock data line chart for each selected ticker, filtered up to the cutoff date
    for i, (ticker, data) in enumerate(selected_stock_data.items()):
        filtered_data = data[data.index <= cutoff_date]
        fig.add_trace(go.Scatter(
            x=filtered_data.index,
            y=filtered_data['indexed_close'],
            mode='lines',
            name=ticker_names[ticker],
            line=dict(width=2, color=colors[i % len(colors)]),
            yaxis='y1',  # Primary y-axis
            visible=True  # Ensure all selected tickers are visible
        ))

    # Plot events as invisible markers for hover tooltip display
    fig.add_trace(go.Scatter(
        x=events_df.index,
        y=[100] * len(events_df),  # Ensures events align with the primary y-axis
        mode='markers',
        name='Event',
        customdata=[split_event_text(event) for event in events_df['event_text']],
        marker=dict(color='blue', size=8, opacity=0),  # Invisible markers
        hovertemplate="<b>Event:</b><br>%{customdata}<extra></extra>"
    ))
    
    bar_color = 'red' if 'colorblind' not in colorblind_mode else colors[-1]
    
    # COVID-19 cases bar chart on secondary y-axis, filtered up to the cutoff date
    filtered_covid_infections = covid_infections[covid_infections.index <= cutoff_date]
    fig.add_trace(go.Bar(
        x=filtered_covid_infections.index,
        y=filtered_covid_infections['new_cases_smoothed'],
        name='COVID-19 Cases (Smoothed)',
        marker=dict(color=bar_color, opacity=0.4),
        yaxis='y2'  # Secondary y-axis
    ))

    # Layout with dual axes
    fig.update_layout(
        title="Indexed Close Price and COVID-19 Cases",
        xaxis=dict(title='Date', range=[selected_stock_data[tickers[0]].index.min(), cutoff_date]),
        yaxis=dict(title='Indexed Price (%)', side='left', showgrid=True),
        yaxis2=dict(title='COVID-19 Cases (Smoothed)', overlaying='y', side='right', showgrid=False),
        hovermode='x unified',
        template='plotly_white',
        hoverlabel=dict(
            bordercolor="white",
            font=dict(family="Arial, sans-serif", size=12, color="black"),
            align="left",
            namelength=0,
        ),
        legend=dict(
            x=0.5,  # Center the legend horizontally
            y=1.05,  # Place it slightly above the plot area
            xanchor='center',  # Anchor horizontally to the center
            orientation="h"  # Make the legend horizontal
        ),
        margin=dict(l=80),  # Increase left margin to create space for y-axis title
    )

    return fig

# Hover data store for line chart hover
@app.callback(
    Output('hover-store', 'data'),
    Input('line-chart', 'hoverData'),
    prevent_initial_call=True
)
def store_hover_data(hover_data):
    if hover_data:
        return hover_data['points'][0]['x']
    return None

@cache.memoize(timeout=3600)
def calculate_heatmap_data():
    # This function retrieves and preprocesses the data for the heatmap only once every hour.
    all_stock_data = pd.DataFrame()
    for ticker in ticker_options.keys():
        stock_data = load_stock_data(ticker)
        if 'close' in stock_data.columns:
            stock_data['price_index'] = stock_data['close'] / stock_data['close'].iloc[0] * 100
            stock_data['ticker'] = ticker
            all_stock_data = pd.concat([all_stock_data, stock_data[['price_index', 'ticker']]], axis=0)
    all_stock_data.reset_index(inplace=True)
    all_stock_data['date'] = all_stock_data['timestamp'].dt.date
    return all_stock_data

@cache.memoize(timeout=600)  # Cache for 10 minutes or adjust as needed
def calculate_heatmap_data_cached():
    return calculate_heatmap_data()

# Updated heatmap callback that shows all stocks in a 4x3 grid, irrespective of selection
@app.callback(
    Output('heatmap-container', 'children'),
    [Input('hover-store', 'data'),
     Input('colorblind-toggle', 'value')]
)
def update_heatmap_on_hover(hovered_date_str, colorblind_mode):
    # Retrieve precomputed heatmap data to avoid redundant processing
    all_stock_data = calculate_heatmap_data_cached()
    if all_stock_data.empty:
        return "No data available for the heatmap."

    # Filter data based on hovered date, if provided
    if hovered_date_str:
        hovered_date = pd.to_datetime(hovered_date_str).date()
        filtered_data = all_stock_data[all_stock_data['date'] == hovered_date]
    else:
        filtered_data = all_stock_data  # Use all data if no hover event

    # Pivot data and handle missing values safely
    heatmap_pivot = filtered_data.pivot_table(index='ticker', columns='date', values='price_index', fill_value=0)
    
    # Prepare 4x3 ticker grid and calculate heatmap values
    tickers_list = list(ticker_options.keys()) + [None] * (12 - len(ticker_options))
    grid_tickers = [tickers_list[i:i+3] for i in range(0, 12, 3)]
    heatmap_values = [[(heatmap_pivot.loc[ticker].values[0] - 100) if ticker in heatmap_pivot.index else None 
                       for ticker in row] for row in grid_tickers]
    
    if colorblind_mode:
        colorscale = [[0.0, "red"], [0.5, "white"], [1.0, "#546494"]]
    else:
        # Explicitly set a palette that includes red
        colorscale = [[0.0, "red"], [0.5, "white"], [1.0, "green"]]

    # Create heatmap figure
    heatmap_fig = go.Figure(data=go.Heatmap(
        z=heatmap_values,
        x=[(f"Column {i+1}") for i in range(3)],
        y=[f"Row {i+1}" for i in range(4)],
        colorscale=colorscale,
        zmin=-100, zmax=100,
        colorbar=dict(title="", tickvals=[-100, 0, 100])
    ))

    heatmap_fig.update_layout(
        title="Stock Price Heatmap based on index price change from the Base Price (100)",
        xaxis=dict(showticklabels=False),  # Hide x-axis tick labels
        yaxis=dict(showticklabels=False)   # Hide y-axis tick labels
    )

    # Add ticker descriptions and values
    for i, row in enumerate(grid_tickers):
        for j, ticker in enumerate(row):
            if ticker:
                price_value = heatmap_pivot.loc[ticker].values[0] if ticker in heatmap_pivot.index else None
                ticker_description = ticker_options.get(ticker, ticker)
                annotation_text = f"{ticker_description}<br>{price_value - 100:.2f}%" if price_value else "N/A"
                heatmap_fig.add_annotation(
                    x=j, y=i, text=annotation_text,
                    showarrow=False, font=dict(color="black", size=10)
                )

    return dcc.Graph(figure=heatmap_fig, config={'displayModeBar': False})