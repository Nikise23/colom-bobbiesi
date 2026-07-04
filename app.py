from consultorio import create_app

app = create_app()

if __name__ == "__main__":
    # use_reloader=False evita errores de SQLAlchemy al recargar en caliente
    app.run(debug=True, use_reloader=False)
