from exporter import create_app

metrics = create_app()

if __name__ == "__main__":
    metrics.run()
